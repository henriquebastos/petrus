"""Application-owned Pi 0.83.0 A5 low-level-loop runtime.

This adapter deliberately does not share the native Pi adapter's session or
operation implementation.  The application owns a bounded JSON transcript;
the helper performs one, and only one, low-level ``runAgentLoop`` invocation.
"""

from __future__ import annotations

import base64
import json
import math
import os
import platform
import re
import selectors
import shutil
import signal
import stat
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp
from typing import Protocol, cast, runtime_checkable

from petrus.agenticus.attachment.binding import MotusAttachmentBinding
from petrus.agenticus.attachment.episode import EpisodeAttachment
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorIdentity, DescriptorKind
from petrus.agenticus.connection.custody import (
    AdmissionResult,
    AttachmentFence,
    CleanupEvidence,
    ConnectionStatus,
    ConnectionView,
    LeaseMode,
    Materialization,
    ReleaseResult,
)
from petrus.agenticus.hands.contract import RejectionCategory, ToolError, ToolMethod, ToolResult
from petrus.agenticus.hands.gateway import HandsGateway
from petrus.agenticus.program.descriptor import AgentProgramDescriptor, ContinuationRequirement, ProgramOwnership
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
from petrus.agenticus.runtime.pi import PI_AI_SOURCE, PI_AI_VERSION, PI_API_KEY_CATALOG, PI_SDK_SOURCE_COMMIT
from petrus.agenticus.runtime.profiles import PI_APPLICATION_A5_E2B, PI_APPLICATION_A5_GONDOLIN
from petrus.agenticus.runtime.result import RuntimeTurnSettlement
from petrus.agenticus.thread.continuation import Continuation, ContinuationDescriptor, ContinuationState
from petrus.agenticus.thread.identity import EpisodeId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome
from petrus.motus.execution import LeaseState

PI_APPLICATION_CODING_AGENT_VERSION = "0.83.0"
PI_APPLICATION_AGENT_CORE_VERSION = "0.83.0"
PI_APPLICATION_AI_VERSION = "0.83.0"
PI_APPLICATION_SOURCE_COMMIT = PI_SDK_SOURCE_COMMIT

_PROGRAM_ID = DescriptorIdentity(DescriptorKind.PROGRAM, "pi.application-owned", 1)
_CONTINUATION_ID = DescriptorIdentity(DescriptorKind.CONTINUATION, "pi.application-owned", 1)
_CONNECTION_ID = DescriptorIdentity(DescriptorKind.CONNECTION, "pi.compatible-api-key", 1)
_HANDS_ID = DescriptorIdentity(DescriptorKind.HANDS, "pi.capability-scoped", 1)
PI_APPLICATION_CONTINUATION_DESCRIPTOR = ContinuationDescriptor(_CONTINUATION_ID, _PROGRAM_ID)
PI_APPLICATION_PROGRAM = AgentProgramDescriptor(
    identity=_PROGRAM_ID,
    ownership=ProgramOwnership.HARNESS,
    accepted_continuations=(ContinuationRequirement(_CONTINUATION_ID, _PROGRAM_ID),),
    produced_continuation=_CONTINUATION_ID,
    owns_steering=True,
    owns_evaluation=True,
)
PI_APPLICATION_PROGRAM_CAPABILITIES = CapabilityDescriptor(_PROGRAM_ID, frozenset({"program.application-owned"}))
PI_APPLICATION_CONTINUATION_CAPABILITIES = CapabilityDescriptor(
    _CONTINUATION_ID, frozenset({"continuation.application-owned"})
)
PI_APPLICATION_CONNECTION_CAPABILITIES = CapabilityDescriptor(_CONNECTION_ID, frozenset({"connection.pi-compatible"}))
PI_APPLICATION_HANDS = CapabilityDescriptor(_HANDS_ID, frozenset({"hands.capability-scoped"}))

_MAX_OBSERVATION = 64 * 1024
_MAX_KEY = 8192
_HELPER_LIMIT = 16 * 1024 * 1024
_METHODS = frozenset(method.value for method in ToolMethod)
_DIGEST = re.compile(r"[0-9a-f]{64}")


def _text(value: object, label: str, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > maximum
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError(f"{label} must be bounded non-empty text")
    return value


def _strict_load(value: bytes) -> object:
    def reject(_: str) -> object:
        raise ValueError

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError
            result[key] = item
        return result

    return json.loads(value.decode("utf-8", "strict"), parse_constant=reject, object_pairs_hook=unique)


def _transcript(value: bytes, maximum: int, messages: int) -> bytes:
    if not isinstance(value, bytes) or len(value) > maximum:
        raise ValueError("Pi application transcript exceeds its byte bound")
    try:
        decoded = _strict_load(value)
    except UnicodeDecodeError, json.JSONDecodeError, ValueError:
        raise ValueError("Pi application transcript must be strict UTF-8 JSON") from None
    if type(decoded) is not list or len(decoded) > messages or any(type(item) is not dict for item in decoded):
        raise ValueError("Pi application transcript must be a bounded message array")
    return value


@dataclass(frozen=True)
class PiApplicationContinuationPayloadV1:
    working_directory_binding: str = field(repr=False)
    transcript_json: bytes = field(repr=False)
    schema_version: int = field(default=1, init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.working_directory_binding, str)
            or _DIGEST.fullmatch(self.working_directory_binding) is None
        ):
            raise ValueError("Pi application working-directory binding must be SHA-256")
        _transcript(self.transcript_json, 4_000_000, 10_000)


@dataclass(frozen=True)
class PiApplicationStepPayloadV1:
    profile: str
    results: tuple[ToolResult, ...] = field(repr=False)
    final_text: str = field(repr=False)
    schema_version: int = field(default=1, init=False)

    def __post_init__(self) -> None:
        if self.profile not in {"gondolin", "e2b"}:
            raise ValueError("Pi application step profile is unsupported")
        results = tuple(self.results)
        if any(not isinstance(result, ToolResult) for result in results):
            raise TypeError("Pi application step results must be ToolResult values")
        object.__setattr__(self, "results", results)
        if not isinstance(self.final_text, str) or len(self.final_text.encode()) > 1_000_000:
            raise ValueError("Pi application final text exceeds its bound")


@runtime_checkable
class PiApplicationContinuationOperations(Protocol):
    def store(self, operation_id: str, payload: PiApplicationContinuationPayloadV1) -> str: ...
    def load(self, state_reference: str) -> PiApplicationContinuationPayloadV1: ...


@runtime_checkable
class PiApplicationTurnOperations(Protocol):
    def store_turn(self, operation_id: str, payload: PiApplicationStepPayloadV1) -> str: ...


class PiApplicationContinuationCodec:
    descriptor = PI_APPLICATION_CONTINUATION_DESCRIPTOR

    def __init__(self, operations: PiApplicationContinuationOperations) -> None:
        if not isinstance(operations, PiApplicationContinuationOperations):
            raise TypeError("Pi application codec requires exact operations")
        self._operations = operations

    def store(self, operation_id: str, payload: PiApplicationContinuationPayloadV1) -> str:
        return _text(
            self._operations.store(_text(operation_id, "Pi application operation"), payload), "state reference", 512
        )

    def load(self, continuation: Continuation) -> PiApplicationContinuationPayloadV1:
        if not isinstance(continuation, Continuation) or continuation.descriptor != self.descriptor:
            raise ValueError("Pi application Continuation does not match this runtime")
        value = self._operations.load(continuation.state_reference)
        if not isinstance(value, PiApplicationContinuationPayloadV1):
            raise TypeError("Pi application custody returned a foreign payload")
        return value


@dataclass(frozen=True)
class PiApplicationRuntimeConfig:
    provider: str
    model: str
    profile: str
    working_directory: Path = field(repr=False)
    runtime_root: Path = field(repr=False)
    host_id: str = "local"
    credential_ttl: float = 315.0
    wall_timeout: float = 300.0
    cancellation_grace: float = 2.0
    max_messages: int = 10_000
    max_transcript_bytes: int = 4_000_000
    max_tool_calls: int = 256
    max_events: int = 10_000
    max_frame_bytes: int = 16 * 1024 * 1024
    max_output_bytes: int = 1_000_000

    def __post_init__(self) -> None:  # noqa: C901 - validates independent security bounds
        for name in ("provider", "model", "host_id"):
            object.__setattr__(self, name, _text(getattr(self, name), f"Pi application {name}"))
        if self.profile not in {"gondolin", "e2b"}:
            raise ValueError("Pi application profile must be gondolin or e2b")
        if (self.provider, self.model) not in PI_API_KEY_CATALOG:
            raise ValueError("Pi application provider/model is outside the direct API-key catalog")
        for name in ("working_directory", "runtime_root"):
            selected = Path(getattr(self, name))
            if selected.is_symlink():
                raise ValueError(f"Pi application {name} must be stable")
            selected = selected.resolve()
            if not selected.is_dir():
                raise ValueError(f"Pi application {name} must exist")
            if name == "runtime_root":
                metadata = selected.stat()
                if stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.geteuid():
                    raise ValueError("Pi application runtime_root must be owned mode-0700")
            object.__setattr__(self, name, selected)
        for name in ("credential_ttl", "wall_timeout", "cancellation_grace"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Pi application {name} must be positive and finite")
        for name in (
            "max_messages",
            "max_transcript_bytes",
            "max_tool_calls",
            "max_events",
            "max_frame_bytes",
            "max_output_bytes",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"Pi application {name} must be positive")
        encoded_transcript = 4 * ((self.max_transcript_bytes + 2) // 3)
        if (
            self.max_frame_bytes > _HELPER_LIMIT
            or self.max_frame_bytes < encoded_transcript + _MAX_OBSERVATION + 128 * 1024
        ):
            raise ValueError("Pi application frame bound cannot carry its transcript")


@dataclass(frozen=True)
class PiApplicationRuntimeInvocation:
    operation_id: str
    episode_id: EpisodeId
    turn_id: TurnId
    observation: str = field(repr=False)
    connection: ConnectionView
    attachment: EpisodeAttachment = field(repr=False)
    gateway: HandsGateway = field(repr=False)
    grant_epoch: int
    continuation: Continuation | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _text(self.operation_id, "Pi application operation"))
        if not isinstance(self.episode_id, EpisodeId) or not isinstance(self.turn_id, TurnId):
            raise TypeError("Pi application invocation requires exact identities")
        if (
            not isinstance(self.observation, str)
            or not self.observation
            or len(self.observation.encode()) > _MAX_OBSERVATION
            or "\0" in self.observation
        ):
            raise ValueError("Pi application observation must be bounded non-empty text")
        if not isinstance(self.connection, ConnectionView) or self.connection.status is not ConnectionStatus.READY:
            raise ValueError("Pi application invocation requires a ready connection")
        if self.connection.identity.profile != "api-key":
            raise ValueError("Pi application accepts only an api-key connection")
        if not isinstance(self.attachment, EpisodeAttachment) or self.attachment.episode_id != self.episode_id:
            raise ValueError("Pi application invocation requires its exact attachment")
        if not isinstance(self.gateway, HandsGateway):
            raise TypeError("Pi application invocation requires HandsGateway")
        coordinates = self.attachment.coordinates()
        if (self.gateway.episode_id, self.gateway.attachment_id, self.gateway.attachment_epoch) != (
            coordinates.episode_id,
            coordinates.attachment_id,
            coordinates.attachment_epoch,
        ):
            raise ValueError("Pi application gateway attachment mismatch")
        if type(self.grant_epoch) is not int or self.grant_epoch <= 0:
            raise ValueError("Pi application grant epoch must be positive")
        if self.continuation is not None and not isinstance(self.continuation, Continuation):
            raise TypeError("Pi application continuation must be Continuation or None")


@dataclass(frozen=True)
class _Candidate:
    text: str = field(repr=False)
    transcript: bytes = field(repr=False)
    results: tuple[ToolResult, ...] = field(repr=False)


class _Client(Protocol):
    def run(
        self,
        gateway: HandsGateway,
        invocation: PiApplicationRuntimeInvocation,
        current: Callable[[], bool],
        deadline: float,
    ) -> _Candidate: ...
    def close(self) -> bool: ...


class _Factory(Protocol):
    def create(self, **kwargs: object) -> _Client: ...


class _SubprocessFactory:
    def __init__(self, helper: Path) -> None:
        self.helper = helper

    def create(self, **kwargs: object) -> _Client:
        return _SubprocessClient(
            node=cast(str, kwargs["node"]),
            coding_entrypoint=cast(str, kwargs["coding_entrypoint"]),
            core_entrypoint=cast(str, kwargs["core_entrypoint"]),
            ai_entrypoint=cast(str, kwargs["ai_entrypoint"]),
            helper=self.helper,
            private_root=cast(Path, kwargs["private_root"]),
            config=cast(PiApplicationRuntimeConfig, kwargs["config"]),
            invocation=cast(PiApplicationRuntimeInvocation, kwargs["invocation"]),
            prior=cast(PiApplicationContinuationPayloadV1 | None, kwargs["prior"]),
            api_key=cast(str, kwargs["api_key"]),
        )


class _SubprocessClient:
    def __init__(
        self,
        *,
        node: str,
        coding_entrypoint: str,
        core_entrypoint: str,
        ai_entrypoint: str,
        helper: Path,
        private_root: Path,
        config: PiApplicationRuntimeConfig,
        invocation: PiApplicationRuntimeInvocation,
        prior: PiApplicationContinuationPayloadV1 | None,
        api_key: str,
    ) -> None:
        self._config, self._inv = config, invocation
        env = {"HOME": str(private_root), "PATH": str(Path(node).parent), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        try:
            self._process = subprocess.Popen(
                (node, str(helper), coding_entrypoint, core_entrypoint, ai_entrypoint),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                start_new_session=True,
                bufsize=0,
            )
        except OSError:
            raise RuntimeProtocolError("helper-launch-failed") from None
        self._stderr = threading.Thread(target=self._drain, daemon=True)
        self._stderr.start()
        self._closed = False
        grant = invocation.attachment.grants().current()
        self._start = {
            "type": "start",
            "version": 1,
            "provider": config.provider,
            "model": config.model,
            "api_key": api_key,
            "cwd": str(config.working_directory),
            "observation": invocation.observation,
            "transcript": base64.b64encode(prior.transcript_json if prior else b"[]").decode(),
            "write_allowed": bool(grant and grant.permits(ToolMethod.WORKSPACE_WRITE)),
            "limits": {
                "frame": config.max_frame_bytes,
                "output": config.max_output_bytes,
                "transcript": config.max_transcript_bytes,
                "messages": config.max_messages,
                "events": config.max_events,
                "tools": config.max_tool_calls,
            },
        }

    def _drain(self) -> None:
        if self._process.stderr is not None:
            while self._process.stderr.read(65536):
                pass

    def _write(self, frame: dict[str, object]) -> None:
        try:
            encoded = json.dumps(frame, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode() + b"\n"
            if len(encoded) > self._config.max_frame_bytes or self._process.stdin is None:
                raise ValueError
            self._process.stdin.write(encoded)
            self._process.stdin.flush()
        except OSError, ValueError:
            raise RuntimeProtocolError("helper-pipe-failed") from None

    def run(  # noqa: C901 - protocol state machine is one fail-closed surface
        self,
        gateway: HandsGateway,
        invocation: PiApplicationRuntimeInvocation,
        current: Callable[[], bool],
        deadline: float,
    ) -> _Candidate:  # noqa: C901
        self._write(cast(dict[str, object], self._start))
        if self._process.stdout is None:
            raise RuntimeProtocolError("helper-pipe-failed")
        selector = selectors.DefaultSelector()
        selector.register(self._process.stdout, selectors.EVENT_READ)
        buffer = bytearray()
        ready = abort = False
        terminal: _Candidate | None = None
        events = tools = 0
        seen: set[str] = set()
        results: list[ToolResult] = []
        try:
            while terminal is None:
                now = time.monotonic()
                if (not current() or now >= deadline) and not abort:
                    self._write({"type": "abort"})
                    abort = True
                    grace = now + self._config.cancellation_grace
                if abort and now >= grace:
                    raise RuntimeProtocolError("cancelled" if not current() else "deadline-exceeded")
                if self._process.poll() is not None and not selector.select(0):
                    break
                for key, _ in selector.select(0.05):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(self._process.stdout)
                        continue
                    buffer.extend(chunk)
                    if len(buffer) > self._config.max_frame_bytes:
                        raise RuntimeProtocolError("frame-overflow")
                    while b"\n" in buffer:
                        if terminal is not None:
                            raise RuntimeProtocolError("frame-order")
                        raw, _, tail = buffer.partition(b"\n")
                        buffer = bytearray(tail)
                        try:
                            frame = _strict_load(bytes(raw))
                        except UnicodeDecodeError, json.JSONDecodeError, ValueError:
                            raise RuntimeProtocolError("malformed-frame") from None
                        if type(frame) is not dict:
                            raise RuntimeProtocolError("malformed-frame")
                        frame = cast(dict[str, object], frame)
                        events += 1
                        if events > self._config.max_events:
                            raise RuntimeProtocolError("event-overflow")
                        kind = frame.get("type")
                        if abort and kind != "failed":
                            raise RuntimeProtocolError("cancelled" if not current() else "deadline-exceeded")
                        if kind == "ready" and not ready and set(frame) == {"type"}:
                            ready = True
                        elif kind in {"tool_call", "guard_blocked"}:
                            expected = {"type", "id", "method", "params"}
                            identity, method, params = frame.get("id"), frame.get("method"), frame.get("params")
                            if (
                                not ready
                                or set(frame) != expected
                                or not isinstance(identity, str)
                                or not identity
                                or len(identity.encode()) > 128
                                or identity in seen
                                or method not in _METHODS
                                or type(params) is not dict
                            ):
                                raise RuntimeProtocolError("malformed-tool-call")
                            seen.add(identity)
                            tools += 1
                            if tools > self._config.max_tool_calls:
                                raise RuntimeProtocolError("tool-overflow")
                            coordinates = invocation.attachment.coordinates()
                            if kind == "guard_blocked":
                                if method != ToolMethod.WORKSPACE_WRITE.value or bool(self._start["write_allowed"]):
                                    raise RuntimeProtocolError("malformed-tool-call")
                                result = ToolResult(
                                    identity,
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
                                        "call_id": identity,
                                        "episode_id": coordinates.episode_id,
                                        "attachment_id": coordinates.attachment_id,
                                        "attachment_epoch": coordinates.attachment_epoch,
                                        "grant_epoch": invocation.grant_epoch,
                                        "method": method,
                                        "params": params,
                                    }
                                )
                            results.append(result)
                            if kind == "tool_call":
                                self._write({"type": "tool_result", "id": identity, "result": result.to_model_data()})
                        elif kind == "complete":
                            if not ready or set(frame) != {"type", "text", "transcript"}:
                                raise RuntimeProtocolError("frame-order")
                            try:
                                text = frame["text"]
                                if not isinstance(text, str) or len(text.encode()) > self._config.max_output_bytes:
                                    raise ValueError
                                encoded = frame["transcript"]
                                if not isinstance(encoded, str):
                                    raise ValueError
                                delta = base64.b64decode(encoded, validate=True)
                                if base64.b64encode(delta).decode("ascii") != encoded:
                                    raise ValueError
                                _transcript(delta, self._config.max_transcript_bytes, self._config.max_messages)
                                prior = cast(str, self._start["transcript"])
                                prior_bytes = base64.b64decode(prior, validate=True)
                                prior_messages = _strict_load(prior_bytes)
                                delta_messages = _strict_load(delta)
                                assert isinstance(prior_messages, list) and isinstance(delta_messages, list)
                                combined = json.dumps(
                                    [*prior_messages, *delta_messages],
                                    separators=(",", ":"),
                                    ensure_ascii=False,
                                    allow_nan=False,
                                ).encode()
                                _transcript(combined, self._config.max_transcript_bytes, self._config.max_messages)
                            except ValueError, TypeError:
                                raise RuntimeProtocolError("malformed-complete") from None
                            terminal = _Candidate(text, combined, tuple(results))
                        elif (
                            kind == "failed"
                            and set(frame) == {"type", "code"}
                            and frame.get("code") in {"aborted", "provider-failed", "protocol-failed"}
                        ):
                            code = str(frame["code"])
                            if code == "aborted" and abort:
                                code = "cancelled" if not current() else "deadline-exceeded"
                            raise RuntimeProtocolError(code)
                        else:
                            raise RuntimeProtocolError("frame-order")
            if abort:
                raise RuntimeProtocolError("cancelled" if not current() else "deadline-exceeded")
            if buffer or terminal is None:
                raise RuntimeProtocolError("terminal-missing")
            if self._process.wait(timeout=self._config.cancellation_grace) != 0:
                raise RuntimeProtocolError("helper-exit-inconsistent")
            return terminal
        finally:
            selector.close()

    def close(self) -> bool:
        if self._closed:
            return self._process.poll() is not None
        self._closed = True
        for stream in (self._process.stdin, self._process.stdout):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        try:
            if self._process.poll() is None:
                os.killpg(self._process.pid, signal.SIGKILL)
            self._process.wait(timeout=self._config.cancellation_grace)
        except OSError, subprocess.TimeoutExpired:
            return False
        self._stderr.join(self._config.cancellation_grace)
        return self._process.poll() is not None and not self._stderr.is_alive()


@runtime_checkable
class PiApplicationConnectionCustody(Protocol):
    def materialize(
        self, connection_id: str, host_id: str, *, mode: LeaseMode, ttl: float, operation_id: str
    ) -> Materialization: ...
    def admit_result(self, fence: AttachmentFence, *, operation_id: str) -> AdmissionResult: ...
    def release(self, materialization: Materialization, *, operation_id: str) -> ReleaseResult: ...


@dataclass(frozen=True)
class _Key:
    digest: str


class _Operation:
    def __init__(
        self,
        adapter: PiApplicationRuntimeAdapter,
        inv: PiApplicationRuntimeInvocation,
        key: _Key,
        prior: PiApplicationContinuationPayloadV1 | None,
        factory: _Factory,
    ) -> None:
        self.adapter, self.inv, self.key, self.prior, self.factory = adapter, inv, key, prior, factory
        self._condition = threading.Condition()
        self._cancelled = self._publishing = False
        self._result: RuntimeTurnSettlement | None = None
        self._cleanup_disposition = RuntimeCleanupDisposition.UNVERIFIED
        self._cleanup: RuntimeOperationCleanup | None = None
        self._thread = threading.Thread(target=self._run, name=f"pi-app-{key.digest[:12]}", daemon=True)

    @property
    def operation_id(self) -> str:
        return self.inv.operation_id

    def start(self) -> None:
        self._thread.start()

    def current(self) -> bool:
        with self._condition:
            return not self._cancelled

    def _run(self) -> None:
        try:
            result, cleanup = self.adapter._execute(self, self.factory)
        except BaseException:
            result, cleanup = (
                self.adapter._settle(self.inv, TurnOutcome.FAILED, 0, "runtime-failed"),
                RuntimeCleanupDisposition.UNVERIFIED,
            )
        with self._condition:
            if self._cancelled and result.outcome is not TurnOutcome.CANCELLED:
                result = self.adapter._settle(self.inv, TurnOutcome.CANCELLED, 0, "cancelled")
            self._result, self._cleanup_disposition = result, cleanup
            self._condition.notify_all()

    def claim(self) -> str | None:
        with self._condition:
            if self._cancelled:
                return "cancelled"
            grant = self.inv.attachment.grants().current()
            if grant is None or grant.grant_epoch != self.inv.grant_epoch:
                return "grant-mismatch"
            if self.adapter._clock() >= min(grant.deadline, self.inv.attachment.deadline):
                return "deadline-exceeded"
            if not self.adapter._binding_current(self.inv):
                return "runtime-territory-lease-required"
            self._publishing = True
            return None

    def wait(self, timeout: float | None = None) -> RuntimeTurnSettlement:
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("Pi application wait timeout must be positive and finite")
        with self._condition:
            if self._cleanup is not None:
                raise RuntimeProtocolError("operation-closed")
            self._condition.wait_for(lambda: self._result is not None, timeout)
            if self._result is None:
                raise TimeoutError("Pi application operation has not settled")
            return self._result

    def cancel(self, reason: str) -> CancellationDisposition:
        _text(reason, "Pi application cancellation reason")
        with self._condition:
            if self._result is not None or self._publishing:
                return CancellationDisposition.TOO_LATE
            if self._cancelled:
                return CancellationDisposition.ALREADY_REQUESTED
            self._cancelled = True
        try:
            self.inv.attachment.cancel(reason)
        except Exception:
            pass
        return CancellationDisposition.REQUESTED

    def close(self) -> RuntimeOperationCleanup:
        with self._condition:
            if self._cleanup is not None:
                return self._cleanup
            if self._result is None and not self._cancelled:
                raise RuntimeProtocolError("operation-active")
        self._thread.join(self.adapter._config.cancellation_grace * 2)
        disposition = self._cleanup_disposition if not self._thread.is_alive() else RuntimeCleanupDisposition.UNVERIFIED
        self._cleanup = RuntimeOperationCleanup(
            self.operation_id,
            disposition,
            "client-not-created"
            if disposition is RuntimeCleanupDisposition.NOT_CREATED
            else "client-closed"
            if disposition is RuntimeCleanupDisposition.CLEAN
            else "cleanup-uncertain",
        )
        return self._cleanup


class PiApplicationRuntimeAdapter:
    program, continuation_descriptor = PI_APPLICATION_PROGRAM, PI_APPLICATION_CONTINUATION_DESCRIPTOR

    def __init__(
        self,
        config: PiApplicationRuntimeConfig,
        codec: PiApplicationContinuationCodec,
        turns: PiApplicationTurnOperations,
        custody: PiApplicationConnectionCustody,
        *,
        clock: Callable[[], float] = time.monotonic,
        client_factory: _Factory | None = None,
    ) -> None:
        if (
            not isinstance(config, PiApplicationRuntimeConfig)
            or not isinstance(codec, PiApplicationContinuationCodec)
            or not isinstance(turns, PiApplicationTurnOperations)
            or not isinstance(custody, PiApplicationConnectionCustody)
        ):
            raise TypeError("Pi application adapter requires exact collaborators")
        self._config, self._codec, self._turns, self._custody, self._clock = config, codec, turns, custody, clock
        self.descriptor = PI_APPLICATION_A5_GONDOLIN if config.profile == "gondolin" else PI_APPLICATION_A5_E2B
        self.territory = DescriptorIdentity(DescriptorKind.TERRITORY, f"motus.{config.profile}", 1)
        self._factory = client_factory
        self._installation: RuntimeInstallation | None = None
        self._node = self._coding = self._core = self._ai = None
        self._operations: dict[str, _Operation] = {}
        self._lock = threading.RLock()

    def __repr__(self) -> str:
        return f"PiApplicationRuntimeAdapter(profile={self._config.profile!r}, provider={self._config.provider!r}, model={self._config.model!r}, ready={self._installation is not None!r})"

    def probe(
        self, *, cli_path: str | None = None, node_path: str | None = None, package_root: str | None = None
    ) -> RuntimeProbeResult:
        cli, node = cli_path or shutil.which("pi"), node_path or shutil.which("node")
        if cli is None or node is None:
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.NOT_INSTALLED,
                    issues=(
                        ProbeIssue("client-not-installed" if cli is None else "node-not-installed", "pi-application"),
                    ),
                )
            )
        try:
            cli_real, node_real = Path(cli).resolve(strict=True), Path(node).resolve(strict=True)
            root = Path(package_root).resolve(strict=True) if package_root else cli_real.parent.parent
            if cli_real != (root / "dist/cli.js").resolve(strict=True):
                raise ValueError
            coding_package = json.loads((root / "package.json").read_text())
            if (
                coding_package.get("name") != "@earendil-works/pi-coding-agent"
                or coding_package.get("version") != PI_APPLICATION_CODING_AGENT_VERSION
            ):
                raise ValueError
            coding = (root / "dist/index.js").resolve(strict=True)
            core = _package(
                root / "node_modules",
                "pi-agent-core",
                "@earendil-works/pi-agent-core",
                PI_APPLICATION_AGENT_CORE_VERSION,
            )
            ai = _package(root / "node_modules", "pi-ai", "@earendil-works/pi-ai", PI_APPLICATION_AI_VERSION)
            if coding_package.get("bin") not in ({"pi": "dist/cli.js"}, "dist/cli.js"):
                raise ValueError
            dependencies = coding_package.get("dependencies", {})
            if dependencies.get("@earendil-works/pi-agent-core") not in {
                "0.83.0",
                "^0.83.0",
                "~0.83.0",
            } or dependencies.get("@earendil-works/pi-ai") not in {"0.83.0", "^0.83.0", "~0.83.0"}:
                raise ValueError
            version = subprocess.run(
                (str(node_real), "--version"), capture_output=True, text=True, check=True, timeout=10
            ).stdout.strip()
            match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", version)
            if match is None or tuple(map(int, match.groups())) < (22, 19, 0):
                raise ValueError
            helper = Path(__file__).with_name("pi_application_helper.mjs").resolve(strict=True)
            checked = subprocess.run(
                (
                    str(node_real),
                    str(helper),
                    str(coding),
                    str(core),
                    str(ai),
                    "--probe",
                    json.dumps(PI_API_KEY_CATALOG),
                ),
                capture_output=True,
                check=False,
                timeout=10,
                env={"HOME": os.devnull, "PATH": str(node_real.parent), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
            )
            if checked.returncode or checked.stderr or checked.stdout != b'{"type":"probe","ok":true}\n':
                raise ValueError
        except OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError:
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.UNAVAILABLE,
                    issues=(ProbeIssue("protocol-unavailable", "pi-application"),),
                )
            )
        installation = RuntimeInstallation(
            self.descriptor.identity,
            1,
            (
                InstalledComponent(
                    "pi-coding-agent",
                    "0.83.0",
                    f"npm:@earendil-works/pi-coding-agent@0.83.0#commit={PI_APPLICATION_SOURCE_COMMIT}",
                ),
                InstalledComponent(
                    "pi-agent-core",
                    "0.83.0",
                    f"npm:@earendil-works/pi-agent-core@0.83.0#commit={PI_APPLICATION_SOURCE_COMMIT}",
                ),
                InstalledComponent("pi-ai", PI_AI_VERSION, PI_AI_SOURCE),
                InstalledComponent("node", version[1:], f"executable:{node_real}"),
            ),
            platform.system().lower() or "unknown",
            platform.machine().lower() or "unknown",
            frozenset({"runtime.cancel", "runtime.continue", "runtime.application-owned", "runtime.split"}),
        )
        with self._lock:
            self._node, self._coding, self._core, self._ai = str(node_real), str(coding), str(core), str(ai)
            if self._factory is None:
                self._factory = _SubprocessFactory(helper)
        return self._record(RuntimeProbeResult(self.descriptor.identity, ProbeDisposition.READY, installation))

    def _record(self, result: RuntimeProbeResult) -> RuntimeProbeResult:
        with self._lock:
            self._installation = result.installation if result.disposition is ProbeDisposition.READY else None
            if self._installation is None:
                self._node = self._coding = self._core = self._ai = None
                if isinstance(self._factory, _SubprocessFactory):
                    self._factory = None
        return result

    def start(self, inv: PiApplicationRuntimeInvocation) -> RuntimeOperation:
        if not isinstance(inv, PiApplicationRuntimeInvocation):
            raise TypeError("Pi application runtime requires its invocation")
        self._validate(inv)
        if inv.continuation and inv.continuation.state is not ContinuationState.IN_USE:
            raise RuntimeProtocolError("continuation-not-claimed")
        prior = self._codec.load(inv.continuation) if inv.continuation else None
        binding = _working_binding(self._config.working_directory)
        if prior and prior.working_directory_binding != binding:
            raise RuntimeProtocolError("continuation-project-mismatch")
        transcript = prior.transcript_json if prior else b"[]"
        _transcript(transcript, self._config.max_transcript_bytes, self._config.max_messages)
        coordinates = inv.attachment.coordinates()
        grant = inv.attachment.grants().current()
        assert grant is not None
        identity = (
            inv.episode_id.value,
            inv.turn_id.value,
            sha256(inv.observation.encode()).hexdigest(),
            sha256(transcript).hexdigest(),
            inv.connection.identity.connection_id,
            inv.connection.identity.provider,
            inv.connection.identity.profile,
            inv.connection.authority_epoch,
            inv.connection.state_version,
            coordinates.attachment_id,
            coordinates.attachment_epoch,
            inv.grant_epoch,
            tuple(sorted(method.value for method in grant.capabilities)),
            self._config.profile,
            self._config.provider,
            self._config.model,
            binding,
        )
        key = _Key(sha256(repr(identity).encode()).hexdigest())
        with self._lock:
            if (
                self._installation is None
                or self._factory is None
                or None in (self._node, self._coding, self._core, self._ai)
            ):
                raise RuntimeProtocolError("runtime-not-ready")
            old = self._operations.get(inv.operation_id)
            if old:
                if old.key != key:
                    raise RuntimeProtocolError("operation-conflict")
                return old
            operation = _Operation(self, inv, key, prior, self._factory)
            self._operations[inv.operation_id] = operation
        try:
            operation.start()
        except BaseException:
            with self._lock:
                if self._operations.get(inv.operation_id) is operation:
                    del self._operations[inv.operation_id]
            raise
        return operation

    def _validate(self, inv: PiApplicationRuntimeInvocation) -> None:
        if inv.connection.identity.provider != self._config.provider:
            raise RuntimeProtocolError("connection-provider-mismatch")
        if inv.connection.identity.profile != "api-key":
            raise RuntimeProtocolError("connection-profile-mismatch")
        expected = {
            DescriptorKind.RUNTIME: self.descriptor.identity,
            DescriptorKind.CONNECTION: _CONNECTION_ID,
            DescriptorKind.PROGRAM: _PROGRAM_ID,
            DescriptorKind.HANDS: _HANDS_ID,
            DescriptorKind.TERRITORY: self.territory,
            DescriptorKind.CONTINUATION: _CONTINUATION_ID,
        }
        if any(
            (descriptor := inv.attachment.snapshot.descriptor(kind)) is None or descriptor.identity != identity
            for kind, identity in expected.items()
        ):
            raise RuntimeProtocolError("resolution-mismatch")
        effect = inv.attachment.snapshot.descriptor(DescriptorKind.EFFECT)
        grant = inv.attachment.grants().current()
        if effect is None or "effect.host-fenced" not in effect.offers:
            raise RuntimeProtocolError("resolution-mismatch")
        if grant is None or grant.grant_epoch != inv.grant_epoch:
            raise RuntimeProtocolError("grant-mismatch")
        if not self._binding_current(inv):
            raise RuntimeProtocolError("runtime-territory-lease-required")

    def _binding_current(self, inv: PiApplicationRuntimeInvocation) -> bool:
        binding = inv.attachment.binding
        if (
            not isinstance(binding, MotusAttachmentBinding)
            or binding.execution.lease.state is not LeaseState.READY
            or binding.execution.lease.provider != self._config.profile
        ):
            return False
        try:
            observed = binding.provider.lookup(binding.lease_identity.operation_id)
        except Exception:
            return False
        return (
            observed is not None
            and observed.identity == binding.lease_identity
            and observed.state is LeaseState.READY
            and observed.provider == self._config.profile
        )

    def _settle(
        self,
        inv: PiApplicationRuntimeInvocation,
        outcome: TurnOutcome,
        appends: int,
        code: str,
        output: str | None = None,
        continuation: str | None = None,
    ) -> RuntimeTurnSettlement:
        return RuntimeTurnSettlement(inv.episode_id, inv.turn_id, outcome, appends, code, output, continuation)

    def _execute(  # noqa: C901 - cleanup and publication precedence remain explicit
        self, operation: _Operation, factory: _Factory
    ) -> tuple[RuntimeTurnSettlement, RuntimeCleanupDisposition]:
        inv, prior = operation.inv, operation.prior
        materialization = client = root = identity = None
        attempted = False
        clean = True
        outcome, code = TurnOutcome.FAILED, "runtime-failed"
        output_ref = continuation_ref = None
        ids = {name: f"{inv.operation_id}.{name}" for name in ("materialize", "admit", "release")}
        deadline = time.monotonic() + min(self._config.wall_timeout, max(0.0, inv.attachment.deadline - self._clock()))
        try:
            if not operation.current():
                raise RuntimeProtocolError("cancelled")
            if deadline <= time.monotonic() or self._clock() >= inv.attachment.deadline:
                raise RuntimeProtocolError("deadline-exceeded")
            attempted = True
            materialization = self._custody.materialize(
                inv.connection.identity.connection_id,
                self._config.host_id,
                mode=LeaseMode.READ,
                ttl=min(self._config.credential_ttl, max(0.001, deadline - time.monotonic())),
                operation_id=ids["materialize"],
            )
            if not isinstance(materialization, Materialization) or materialization.mode is not LeaseMode.READ:
                raise RuntimeProtocolError("custody-materialization-mismatch")
            fence = materialization.fence
            if not isinstance(fence, AttachmentFence) or (
                fence.connection_id,
                fence.host_id,
                fence.authority_epoch,
                fence.base_version,
            ) != (
                inv.connection.identity.connection_id,
                self._config.host_id,
                inv.connection.authority_epoch,
                inv.connection.state_version,
            ):
                raise RuntimeProtocolError("custody-state-mismatch")
            credential = materialization.home.read()
            if not isinstance(credential, bytes) or not credential or len(credential) > _MAX_KEY:
                raise RuntimeProtocolError("credential-invalid")
            try:
                api_key = credential.decode("utf-8", "strict")
                _text(api_key, "Pi application credential", _MAX_KEY)
            except UnicodeDecodeError, ValueError:
                raise RuntimeProtocolError("credential-invalid") from None
            root = Path(mkdtemp(prefix="operation-", dir=self._config.runtime_root))
            os.chmod(root, 0o700)
            metadata = root.lstat()
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o700
                or metadata.st_uid != os.geteuid()
            ):
                raise RuntimeProtocolError("private-root-invalid")
            identity = (metadata.st_dev, metadata.st_ino)
            client = factory.create(
                node=cast(str, self._node),
                coding_entrypoint=cast(str, self._coding),
                core_entrypoint=cast(str, self._core),
                ai_entrypoint=cast(str, self._ai),
                private_root=root,
                config=self._config,
                invocation=inv,
                prior=prior,
                api_key=api_key,
            )
            candidate = client.run(inv.gateway, inv, operation.current, deadline)
            clean = client.close() and clean
            client = None
            clean = _remove_root(root, identity) and clean
            root = None
            if not clean:
                raise RuntimeProtocolError("private-cleanup-uncertain")
            if error := operation.claim():
                raise RuntimeProtocolError(error)
            admission = self._custody.admit_result(fence, operation_id=ids["admit"])
            if (
                not isinstance(admission, AdmissionResult)
                or admission.operation_id != ids["admit"]
                or admission.purpose != "result"
                or admission.attachment_id != fence.attachment_id
            ):
                raise RuntimeProtocolError("custody-admission-mismatch")
            output_ref = _text(
                self._turns.store_turn(
                    inv.operation_id,
                    PiApplicationStepPayloadV1(self._config.profile, candidate.results, candidate.text),
                ),
                "Pi application output reference",
                512,
            )
            continuation_ref = self._codec.store(
                inv.operation_id,
                PiApplicationContinuationPayloadV1(
                    _working_binding(self._config.working_directory),
                    candidate.transcript,
                ),
            )
            outcome, code = TurnOutcome.COMPLETED, "turn-completed"
        except RuntimeProtocolError as error:
            code = error.code
            outcome = TurnOutcome.CANCELLED if not operation.current() or code == "cancelled" else TurnOutcome.FAILED
            if outcome is TurnOutcome.CANCELLED:
                code = "cancelled"
        except Exception:
            outcome = TurnOutcome.CANCELLED if not operation.current() else TurnOutcome.FAILED
            code = "cancelled" if outcome is TurnOutcome.CANCELLED else "runtime-failed"
        finally:
            if client is not None:
                clean = client.close() and clean
            if root is not None:
                clean = _remove_root(root, identity) and clean
            if materialization is not None:
                try:
                    clean = (
                        _release_verified(
                            self._custody.release(materialization, operation_id=ids["release"]),
                            ids["release"],
                            materialization.fence.attachment_id,
                        )
                        and clean
                    )
                except Exception:
                    clean = False
        if not clean:
            return self._settle(inv, TurnOutcome.FAILED, 0, "cleanup-unverified"), RuntimeCleanupDisposition.UNVERIFIED
        if outcome is not TurnOutcome.COMPLETED:
            output_ref = continuation_ref = None
        return self._settle(
            inv, outcome, 1 if outcome is TurnOutcome.COMPLETED else 0, code, output_ref, continuation_ref
        ), RuntimeCleanupDisposition.CLEAN if attempted else RuntimeCleanupDisposition.NOT_CREATED


def _package(root: Path, directory: str, name: str, version: str) -> Path:
    candidates = (
        root / "node_modules" / "@earendil-works" / directory,
        root / "@earendil-works" / directory,
        root / directory,
    )
    package_root = next((candidate for candidate in candidates if candidate.is_dir()), None)
    if package_root is None:
        raise ValueError
    package = json.loads((package_root / "package.json").read_text())
    if package.get("name") != name or package.get("version") != version:
        raise ValueError
    return (package_root / "dist/index.js").resolve(strict=True)


def _working_binding(path: Path) -> str:
    return sha256(f"pi-application:{path}".encode()).hexdigest()


def _release_verified(value: object, operation_id: str, attachment_id: str) -> bool:
    return (
        isinstance(value, ReleaseResult)
        and value.operation_id == operation_id
        and isinstance(value.cleanup, CleanupEvidence)
        and value.cleanup.attachment_id == attachment_id
        and (value.cleanup.removed or value.cleanup.already_absent)
        and not value.cleanup.security_violation
    )


def _remove_root(path: Path, identity: tuple[int, int] | None) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return True
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or identity != (metadata.st_dev, metadata.st_ino)
    ):
        return False
    try:
        shutil.rmtree(path)
    except OSError:
        return False
    return not os.path.lexists(path)


__all__ = [
    "PI_APPLICATION_AGENT_CORE_VERSION",
    "PI_APPLICATION_AI_VERSION",
    "PI_APPLICATION_CODING_AGENT_VERSION",
    "PI_APPLICATION_CONNECTION_CAPABILITIES",
    "PI_APPLICATION_CONTINUATION_CAPABILITIES",
    "PI_APPLICATION_CONTINUATION_DESCRIPTOR",
    "PI_APPLICATION_HANDS",
    "PI_APPLICATION_PROGRAM",
    "PI_APPLICATION_PROGRAM_CAPABILITIES",
    "PI_APPLICATION_SOURCE_COMMIT",
    "PiApplicationConnectionCustody",
    "PiApplicationContinuationCodec",
    "PiApplicationContinuationOperations",
    "PiApplicationContinuationPayloadV1",
    "PiApplicationRuntimeAdapter",
    "PiApplicationRuntimeConfig",
    "PiApplicationRuntimeInvocation",
    "PiApplicationStepPayloadV1",
    "PiApplicationTurnOperations",
]
