"""Exact Claude A2 Local runtime; the optional SDK is loaded only at its boundary."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import importlib
import importlib.metadata
import inspect
import json
import math
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict, dataclass, field, is_dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from petrus.agenticus.attachment.binding import MotusAttachmentBinding
from petrus.agenticus.attachment.episode import EpisodeAttachment
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorIdentity, DescriptorKind
from petrus.agenticus.connection.custody import (
    AdmissionResult,
    AttachmentFence,
    ConnectionStatus,
    ConnectionView,
    CleanupEvidence,
    LeaseMode,
    Materialization,
    ReleaseResult,
)
from petrus.agenticus.hands.contract import (
    MAX_ARGV_PART_CHARS,
    MAX_ARGV_PARTS,
    MAX_CONTENT_CHARS,
    MAX_CWD_CHARS,
    MAX_PATH_CHARS,
    MAX_QUERY_CHARS,
    ToolMethod,
)
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
from petrus.agenticus.runtime.profiles import CLAUDE_A2_LOCAL
from petrus.agenticus.runtime.result import RuntimeTurnSettlement
from petrus.agenticus.thread.continuation import Continuation, ContinuationDescriptor, ContinuationState
from petrus.agenticus.thread.identity import EpisodeId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome
from petrus.motus.execution import LeaseState

CLAUDE_SDK_VERSION = "0.2.128"
CLAUDE_SDK_SOURCE_COMMIT = "ec776735b0eb8a8286827a005b35be1782e1940c"
CLAUDE_CODE_VERSION = "2.1.220"
CLAUDE_CODE_DISTRIBUTION_COMMIT = "7ef6eec9d9ba84ea6f233f26c45f1df5c5991843"
CLAUDE_SDK_SOURCE = f"pypi:claude-agent-sdk=={CLAUDE_SDK_VERSION}#commit={CLAUDE_SDK_SOURCE_COMMIT}"
CLAUDE_CODE_SOURCE = f"bundled:claude-code=={CLAUDE_CODE_VERSION}#commit={CLAUDE_CODE_DISTRIBUTION_COMMIT}"

_PROGRAM_ID = DescriptorIdentity(DescriptorKind.PROGRAM, "claude.provider-managed", 1)
_CONTINUATION_ID = DescriptorIdentity(DescriptorKind.CONTINUATION, "claude.native", 1)
_CONNECTION_ID = DescriptorIdentity(DescriptorKind.CONNECTION, "claude.api-key", 1)
_HANDS_ID = DescriptorIdentity(DescriptorKind.HANDS, "claude.collocated", 1)
_TERRITORY_ID = DescriptorIdentity(DescriptorKind.TERRITORY, "motus.local", 1)
CLAUDE_CONTINUATION_DESCRIPTOR = ContinuationDescriptor(_CONTINUATION_ID, _PROGRAM_ID)
CLAUDE_PROGRAM = AgentProgramDescriptor(
    identity=_PROGRAM_ID,
    ownership=ProgramOwnership.PROVIDER,
    accepted_continuations=(ContinuationRequirement(_CONTINUATION_ID, _PROGRAM_ID),),
    produced_continuation=_CONTINUATION_ID,
    owns_steering=False,
    owns_evaluation=False,
)
CLAUDE_PROGRAM_CAPABILITIES = CapabilityDescriptor(_PROGRAM_ID, frozenset({"program.provider-owned"}))
CLAUDE_CONTINUATION_CAPABILITIES = CapabilityDescriptor(_CONTINUATION_ID, frozenset({"continuation.claude-native"}))
CLAUDE_CONNECTION_CAPABILITIES = CapabilityDescriptor(_CONNECTION_ID, frozenset({"connection.claude"}))
CLAUDE_COLLOCATED_HANDS = CapabilityDescriptor(_HANDS_ID, frozenset({"hands.collocated"}))
CLAUDE_LOCAL_TERRITORY = CapabilityDescriptor(_TERRITORY_ID, frozenset())

_TOOLS = tuple(f"mcp__petrus_hands__{method.value}" for method in ToolMethod)
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
_ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
_MAX_PROMPT_BYTES = 64 * 1024
_MAX_TRANSCRIPT_ENTRIES = 10_000
_MAX_TRANSCRIPT_BYTES = 4_000_000
_MIN_DISCONNECT_TIMEOUT = 25
_AUTH_ENVIRONMENT = {
    "ANTHROPIC_AUTH_TOKEN": "",
    "ANTHROPIC_BASE_URL": "",
    "ANTHROPIC_MODEL": "",
    "CLAUDE_CODE_OAUTH_TOKEN": "",
    "CLAUDE_CODE_USE_BEDROCK": "",
    "CLAUDE_CODE_USE_FOUNDRY": "",
    "CLAUDE_CODE_USE_VERTEX": "",
    "AWS_ACCESS_KEY_ID": "",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI": "",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": "",
    "AWS_PROFILE": "",
    "AWS_SECRET_ACCESS_KEY": "",
    "AWS_SESSION_TOKEN": "",
    "AWS_WEB_IDENTITY_TOKEN_FILE": "",
    "AZURE_CLIENT_ID": "",
    "AZURE_CLIENT_SECRET": "",
    "AZURE_TENANT_ID": "",
    "GOOGLE_APPLICATION_CREDENTIALS": "",
    "GOOGLE_CLOUD_PROJECT": "",
}

_TOOL_SCHEMAS: dict[ToolMethod, dict[str, object]] = {
    ToolMethod.WORKSPACE_READ: {
        "type": "object",
        "properties": {"path": {"type": "string", "minLength": 1, "maxLength": MAX_PATH_CHARS}},
        "required": ["path"],
        "additionalProperties": False,
    },
    ToolMethod.WORKSPACE_SEARCH: {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": MAX_QUERY_CHARS},
            "path": {"type": "string", "minLength": 1, "maxLength": MAX_PATH_CHARS},
        },
        "required": ["query", "path"],
        "additionalProperties": False,
    },
    ToolMethod.WORKSPACE_SHELL: {
        "type": "object",
        "properties": {
            "argv": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_ARGV_PARTS,
                "items": {"type": "string", "minLength": 1, "maxLength": MAX_ARGV_PART_CHARS},
            },
            "cwd": {"type": "string", "minLength": 1, "maxLength": MAX_CWD_CHARS},
        },
        "required": ["argv", "cwd"],
        "additionalProperties": False,
    },
    ToolMethod.WORKSPACE_WRITE: {
        "type": "object",
        "properties": {
            "path": {"type": "string", "minLength": 1, "maxLength": MAX_PATH_CHARS},
            "content": {"type": "string", "maxLength": MAX_CONTENT_CHARS},
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    },
    ToolMethod.WORKSPACE_TEST: {"type": "object", "properties": {}, "additionalProperties": False},
}


def _text(value: object, name: str, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{name} must be bounded non-empty text")
    return value


def _positive_number(value: object, name: str, *, minimum: float = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"Claude {name} must be positive")
    if value < minimum:
        raise ValueError(f"Claude {name} must satisfy the pinned SDK cleanup bound")


def _uuid(value: object) -> str:
    value = _text(value, "Claude session identity", 36)
    try:
        parsed = UUID(value)
    except ValueError, AttributeError:
        raise ValueError("Claude session identity must be a canonical UUID") from None
    if str(parsed) != value or _UUID.fullmatch(value) is None:
        raise ValueError("Claude session identity must be a canonical UUID")
    return value


def _json_entries(value: object, maximum_entries: int, maximum_total: int) -> tuple[dict[str, object], ...]:
    if not isinstance(value, (list, tuple)) or not value or len(value) > maximum_entries:
        raise ValueError("Claude transcript must be one bounded non-empty entry batch")
    try:
        encoded = json.dumps(
            value,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
        ).encode()
        copied = json.loads(encoded)
    except TypeError, ValueError:
        raise ValueError("Claude transcript must contain strict JSON entries") from None
    if len(encoded) > maximum_total or any(type(entry) is not dict for entry in copied):
        raise ValueError("Claude transcript exceeds its entry or total bound")
    return tuple(copied)


def _encode_transcript(value: object, maximum_entries: int, maximum_total: int) -> bytes:
    entries = _json_entries(value, maximum_entries, maximum_total)
    return json.dumps(entries, separators=(",", ":"), ensure_ascii=False, sort_keys=True).encode()


def _decode_transcript(value: object, maximum_entries: int, maximum_total: int) -> tuple[dict[str, object], ...]:
    if not isinstance(value, bytes) or not value or len(value) > maximum_total:
        raise ValueError("Claude transcript must be non-empty bounded opaque bytes")
    try:
        decoded = json.loads(value)
    except UnicodeDecodeError, json.JSONDecodeError:
        raise ValueError("Claude transcript must be strict JSON bytes") from None
    entries = _json_entries(decoded, maximum_entries, maximum_total)
    if _encode_transcript(entries, maximum_entries, maximum_total) != value:
        raise ValueError("Claude transcript bytes must use the canonical immutable encoding")
    return entries


@dataclass(frozen=True)
class ClaudeContinuationPayloadV1:
    session_id: str = field(repr=False)
    project_binding: str = field(repr=False)
    project_key: str = field(repr=False)
    transcript: bytes = field(repr=False)
    schema_version: int = field(default=1, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _uuid(self.session_id))
        binding = _text(self.project_binding, "Claude project binding", 64)
        if re.fullmatch(r"[0-9a-f]{64}", binding) is None:
            raise ValueError("Claude project binding must be a SHA-256 digest")
        object.__setattr__(self, "project_binding", binding)
        object.__setattr__(self, "project_key", _text(self.project_key, "Claude project key", 512))
        _decode_transcript(self.transcript, _MAX_TRANSCRIPT_ENTRIES, _MAX_TRANSCRIPT_BYTES)


@runtime_checkable
class ClaudeContinuationOperations(Protocol):
    def store(self, operation_id: str, payload: ClaudeContinuationPayloadV1) -> str: ...
    def load(self, state_reference: str) -> ClaudeContinuationPayloadV1: ...


@runtime_checkable
class ClaudeTurnOperations(Protocol):
    def store_turn(self, operation_id: str, final_text: str) -> str: ...


class ClaudeContinuationCodec:
    descriptor = CLAUDE_CONTINUATION_DESCRIPTOR

    def __init__(self, operations: ClaudeContinuationOperations) -> None:
        if not isinstance(operations, ClaudeContinuationOperations):
            raise TypeError("Claude codec requires ClaudeContinuationOperations")
        self._operations = operations

    def store(self, operation_id: str, payload: ClaudeContinuationPayloadV1) -> str:
        return _text(self._operations.store(_text(operation_id, "Claude operation"), payload), "state reference", 512)

    def load(self, continuation: Continuation) -> ClaudeContinuationPayloadV1:
        if not isinstance(continuation, Continuation) or continuation.descriptor != self.descriptor:
            raise ValueError("Claude Continuation does not match this runtime")
        value = self._operations.load(continuation.state_reference)
        if not isinstance(value, ClaudeContinuationPayloadV1):
            raise TypeError("Claude custody returned a foreign payload")
        return value


class _SessionStore:
    """Bounded main-transcript mirror implementing the public SDK protocol by shape."""

    def __init__(
        self,
        *,
        max_entries: int,
        max_total_bytes: int,
        project_key: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self._max_entries, self._max_total = max_entries, max_total_bytes
        self._entries: list[dict[str, object]] = []
        self._uuids: dict[str, dict[str, object]] = {}
        self._project_key = project_key
        self._session_id = session_id
        self.failed = False
        self._lock = asyncio.Lock()

    async def append(self, key: object, entries: list[dict[str, object]]) -> None:
        try:
            project_key, session_id = self._validate_key(key)
            if not isinstance(entries, list):
                raise ValueError
            if not entries:
                return
            async with self._lock:
                self._append(project_key, session_id, entries)
        except Exception:
            self.failed = True
            raise RuntimeError("session-store-failed") from None

    def _append(self, project_key: str, session_id: str, entries: list[dict[str, object]]) -> None:
        if self._project_key is None:
            self._project_key = project_key
        if self._session_id is None:
            self._session_id = session_id
        if project_key != self._project_key or session_id != self._session_id:
            raise ValueError
        incoming = _json_entries(entries, self._max_entries, self._max_total)
        candidate = copy.deepcopy(self._entries)
        uuids = copy.deepcopy(self._uuids)
        for entry in incoming:
            identity = entry.get("uuid")
            if identity is not None:
                if not isinstance(identity, str):
                    raise ValueError
                prior = uuids.get(identity)
                if prior is not None:
                    if prior != entry:
                        raise ValueError
                    continue
                uuids[identity] = entry
            candidate.append(entry)
        checked = _json_entries(candidate, self._max_entries, self._max_total)
        self._entries, self._uuids = list(checked), uuids

    async def load(self, key: object) -> list[dict[str, object]] | None:
        try:
            project_key, session_id = self._validate_key(key)
        except ValueError:
            return None
        if project_key != self._project_key or session_id != self._session_id:
            return None
        async with self._lock:
            return copy.deepcopy(self._entries) or None

    def seed(self, transcript: bytes) -> None:
        if self._entries:
            raise RuntimeProtocolError("session-store-conflict")
        if self._project_key is None or self._session_id is None:
            raise RuntimeProtocolError("session-store-conflict")
        try:
            checked = _decode_transcript(transcript, self._max_entries, self._max_total)
        except ValueError:
            raise RuntimeProtocolError("session-store-conflict") from None
        self._entries = list(copy.deepcopy(checked))
        for entry in checked:
            identity = entry.get("uuid")
            if isinstance(identity, str):
                if identity in self._uuids and self._uuids[identity] != entry:
                    raise RuntimeProtocolError("session-store-conflict")
                self._uuids[identity] = entry

    def snapshot(self, session_id: str) -> tuple[str, bytes]:
        if self.failed or self._project_key is None or self._session_id != session_id or not self._entries:
            raise RuntimeProtocolError("session-store-failed")
        return self._project_key, _encode_transcript(self._entries, self._max_entries, self._max_total)

    @staticmethod
    def _validate_key(key: object) -> tuple[str, str]:
        if not isinstance(key, dict) or set(key) not in ({"project_key", "session_id"},):
            raise ValueError
        project_key = _text(key.get("project_key"), "Claude session project key", 512)
        session_id = _uuid(key.get("session_id"))
        return project_key, session_id


@dataclass(frozen=True)
class ClaudeRuntimeConfig:
    model: str
    working_directory: Path = field(repr=False)
    runtime_root: Path = field(repr=False)
    host_id: str = "local"
    credential_ttl: float = 300
    max_turns: int = 32
    max_budget_usd: float = 10
    wall_timeout: float = 300
    cancellation_grace: float = 10
    disconnect_timeout: float = _MIN_DISCONNECT_TIMEOUT
    max_messages: int = 10_000
    max_message_bytes: int = 1_000_000
    max_transcript_bytes: int = 4_000_000
    sdk_version: str = CLAUDE_SDK_VERSION
    cli_version: str = CLAUDE_CODE_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "model", _text(self.model, "Claude model", 256))
        object.__setattr__(self, "host_id", _text(self.host_id, "Claude host"))
        for name in ("working_directory", "runtime_root"):
            selected = Path(getattr(self, name))
            if selected.is_symlink():
                raise ValueError(f"Claude {name} must be an existing stable directory")
            path = selected.resolve()
            if not path.is_dir():
                raise ValueError(f"Claude {name} must be an existing stable directory")
            metadata = path.stat()
            if name == "runtime_root" and ((metadata.st_mode & 0o777) != 0o700 or metadata.st_uid != os.geteuid()):
                raise ValueError("Claude runtime_root must be an owned mode-0700 directory")
            object.__setattr__(self, name, path)
        for name in ("max_turns", "max_messages", "max_message_bytes", "max_transcript_bytes"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"Claude {name} must be positive")
        for name in ("credential_ttl", "max_budget_usd", "wall_timeout", "cancellation_grace", "disconnect_timeout"):
            value = getattr(self, name)
            _positive_number(
                value,
                name,
                minimum=_MIN_DISCONNECT_TIMEOUT if name == "disconnect_timeout" else 0,
            )
        if self.sdk_version != CLAUDE_SDK_VERSION or self.cli_version != CLAUDE_CODE_VERSION:
            raise ValueError("Claude requires the exact qualified SDK and CLI pair")


@dataclass(frozen=True)
class ClaudeRuntimeInvocation:
    operation_id: str
    episode_id: EpisodeId
    turn_id: TurnId
    prompt: str = field(repr=False)
    connection: ConnectionView
    attachment: EpisodeAttachment = field(repr=False)
    gateway: HandsGateway = field(repr=False)
    grant_epoch: int
    continuation: Continuation | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _text(self.operation_id, "Claude operation"))
        if not isinstance(self.episode_id, EpisodeId) or not isinstance(self.turn_id, TurnId):
            raise TypeError("Claude invocation requires exact EpisodeId and TurnId")
        if (
            not isinstance(self.prompt, str)
            or not self.prompt
            or len(self.prompt.encode()) > _MAX_PROMPT_BYTES
            or "\x00" in self.prompt
        ):
            raise ValueError("Claude prompt must be bounded non-empty text")
        if (
            not isinstance(self.connection, ConnectionView)
            or self.connection.status is not ConnectionStatus.READY
            or self.connection.identity.provider != "claude"
            or self.connection.identity.profile != "api-key"
        ):
            raise ValueError("Claude invocation requires the ready Claude api-key profile")
        if not isinstance(self.attachment, EpisodeAttachment) or self.attachment.episode_id != self.episode_id:
            raise ValueError("Claude invocation requires its exact Episode Attachment")
        if not isinstance(self.gateway, HandsGateway):
            raise TypeError("Claude invocation requires an exact HandsGateway")
        coordinates = self.attachment.coordinates()
        if (
            self.gateway.episode_id != coordinates.episode_id
            or self.gateway.attachment_id != coordinates.attachment_id
            or self.gateway.attachment_epoch != coordinates.attachment_epoch
        ):
            raise ValueError("Claude gateway does not match the attachment epoch")
        if type(self.grant_epoch) is not int or self.grant_epoch <= 0:
            raise ValueError("Claude grant epoch must be positive")
        if self.continuation is not None and not isinstance(self.continuation, Continuation):
            raise TypeError("Claude continuation must be Continuation or None")


@dataclass(frozen=True)
class _Result:
    subtype: str
    is_error: bool
    session_id: str = field(repr=False)
    terminal_reason: str | None
    text: str | None = field(repr=False)
    encoded_size: int


@dataclass(frozen=True)
class _MirrorError:
    encoded_size: int


@dataclass(frozen=True)
class _Event:
    encoded_size: int


class _Client(Protocol):
    async def connect(self, prompt: str | None = None) -> None: ...
    async def query(self, prompt: str, session_id: str = "default") -> None: ...
    def receive_response(self) -> AsyncIterator[object]: ...
    async def interrupt(self) -> None: ...
    async def disconnect(self) -> None: ...


class _ClientFactory(Protocol):
    def create(
        self,
        options: dict[str, object],
        gateway: HandsGateway,
        invocation: ClaudeRuntimeInvocation,
    ) -> _Client: ...


class _OfficialFactory:
    def __init__(self, sdk: Any) -> None:
        self.sdk = sdk

    def create(self, options: dict[str, object], gateway: HandsGateway, invocation: ClaudeRuntimeInvocation) -> _Client:
        sdk = self.sdk
        pending: dict[tuple[str, bytes], deque[str]] = {}
        pending_lock = asyncio.Lock()

        async def hook(data: dict[str, Any], _tool_use_id: str | None, _context: object) -> dict[str, object]:
            name, call, arguments = data.get("tool_name"), data.get("tool_use_id"), data.get("tool_input")
            try:
                if (
                    name not in _TOOLS
                    or not isinstance(call, str)
                    or "agent_id" in data
                    or "agent_type" in data
                    or not isinstance(arguments, dict)
                ):
                    raise ValueError
                call = _text(call, "Claude tool call identity")
                correlation = (name, _canonical_input(arguments))
            except TypeError, ValueError:
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": "unsupported-tool",
                    }
                }
            async with pending_lock:
                pending.setdefault(correlation, deque()).append(call)
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}

        tools = []
        for full_name, method in zip(_TOOLS, ToolMethod, strict=True):

            async def handler(arguments: dict[str, object], *, _full=full_name, _method=method) -> dict[str, object]:
                try:
                    correlation = (_full, _canonical_input(arguments))
                except TypeError, ValueError:
                    correlation = None
                async with pending_lock:
                    calls = None if correlation is None else pending.get(correlation)
                    call = None if not calls else calls.popleft()
                    if calls is not None and not calls:
                        pending.pop(correlation, None)
                if call is None:
                    return {"content": [{"type": "text", "text": "unsupported-tool"}], "is_error": True}
                c = invocation.attachment.coordinates()
                result = await asyncio.to_thread(
                    gateway.submit,
                    {
                        "version": 1,
                        "call_id": call,
                        "episode_id": c.episode_id,
                        "attachment_id": c.attachment_id,
                        "attachment_epoch": c.attachment_epoch,
                        "grant_epoch": invocation.grant_epoch,
                        "method": _method.value,
                        "params": arguments,
                    },
                )
                return {
                    "content": [{"type": "text", "text": json.dumps(result.to_data(), separators=(",", ":"))}],
                    "is_error": not result.ok,
                }

            tools.append(sdk.tool(method.value, "Agenticus workspace capability", _TOOL_SCHEMAS[method])(handler))
        options["mcp_servers"] = {"petrus_hands": sdk.create_sdk_mcp_server("petrus_hands", tools=tools)}
        options["hooks"] = {"PreToolUse": [sdk.HookMatcher(matcher=None, hooks=[hook])]}
        raw = sdk.ClaudeSDKClient(options=sdk.ClaudeAgentOptions(**options))
        return _OfficialClient(raw, sdk)


class _OfficialClient:
    def __init__(self, client: Any, sdk: Any) -> None:
        self.client, self.sdk = client, sdk

    async def connect(self, prompt: str | None = None) -> None:
        await self.client.connect(prompt)

    async def query(self, prompt: str, session_id: str = "default") -> None:
        await self.client.query(prompt, session_id)

    async def interrupt(self) -> None:
        await self.client.interrupt()

    async def disconnect(self) -> None:
        materialized = getattr(self.client, "_materialized", None)
        config_dir = getattr(materialized, "config_dir", None)
        transport = getattr(self.client, "_transport", None)
        process = getattr(transport, "_process", None)
        await self.client.disconnect()
        if process is not None and getattr(process, "returncode", None) is None:
            raise RuntimeProtocolError("client-cleanup-uncertain")
        if config_dir is not None:
            try:
                Path(config_dir).lstat()
            except FileNotFoundError:
                pass
            except OSError:
                raise RuntimeProtocolError("private-cleanup-uncertain") from None
            else:
                raise RuntimeProtocolError("private-cleanup-uncertain")

    async def receive_response(self) -> AsyncIterator[object]:
        async for message in self.client.receive_response():
            size = _message_size(message)
            if isinstance(message, self.sdk.ResultMessage):
                yield _Result(
                    message.subtype,
                    message.is_error,
                    message.session_id,
                    message.terminal_reason,
                    message.result,
                    size,
                )
            elif isinstance(message, self.sdk.MirrorErrorMessage):
                yield _MirrorError(size)
            elif isinstance(
                message,
                (
                    self.sdk.UserMessage,
                    self.sdk.AssistantMessage,
                    self.sdk.SystemMessage,
                    self.sdk.StreamEvent,
                    self.sdk.RateLimitEvent,
                ),
            ):
                yield _Event(size)
            else:
                raise RuntimeProtocolError("unknown-message")


def _canonical_input(value: object) -> bytes:
    if not isinstance(value, dict) or any(type(key) is not str for key in value):
        raise ValueError("Claude tool input must be a JSON object")
    try:
        encoded = json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False).encode()
    except TypeError, ValueError:
        raise ValueError("Claude tool input must be strict JSON") from None
    if len(encoded) > 8192:
        raise ValueError("Claude tool input exceeds its protocol bound")
    return encoded


def _message_size(message: object) -> int:
    if not is_dataclass(message) or isinstance(message, type):
        raise RuntimeProtocolError("malformed-message")
    try:
        encoded = json.dumps(
            asdict(message),
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
        ).encode()
    except TypeError, ValueError:
        raise RuntimeProtocolError("malformed-message") from None
    return len(encoded)


@runtime_checkable
class ClaudeConnectionCustody(Protocol):
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
        adapter: ClaudeRuntimeAdapter,
        inv: ClaudeRuntimeInvocation,
        key: _Key,
        prior: ClaudeContinuationPayloadV1 | None,
        factory: _ClientFactory,
    ) -> None:
        self.adapter, self.inv, self.key, self.prior, self.factory = adapter, inv, key, prior, factory
        self._condition, self._cancelled, self._publishing = threading.Condition(), False, False
        self._result: RuntimeTurnSettlement | None = None
        self._cleanup = RuntimeCleanupDisposition.UNVERIFIED
        self._closed: RuntimeOperationCleanup | None = None
        self._client: _Client | None = None
        self._thread = threading.Thread(
            target=self._run, name=f"claude-{sha256(inv.operation_id.encode()).hexdigest()[:12]}", daemon=True
        )

    @property
    def operation_id(self) -> str:
        return self.inv.operation_id

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        try:
            result, cleanup = asyncio.run(self.adapter._execute(self, self.factory))
        except BaseException:
            result = self.adapter._settle(self.inv, TurnOutcome.FAILED, 0, "runtime-failed")
            cleanup = RuntimeCleanupDisposition.UNVERIFIED
        with self._condition:
            if self._cancelled and result.outcome is not TurnOutcome.CANCELLED:
                result = self.adapter._settle(self.inv, TurnOutcome.CANCELLED, 0, "cancelled")
            self._result, self._cleanup = result, cleanup
            self._condition.notify_all()

    def wait(self, timeout: float | None = None) -> RuntimeTurnSettlement:
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("Claude operation wait timeout must be positive and finite")
        with self._condition:
            if self._closed:
                raise RuntimeProtocolError("operation-closed")
            self._condition.wait_for(lambda: self._result is not None, timeout)
            if self._result is None:
                raise TimeoutError("Claude operation has not settled")
            return self._result

    def cancel(self, reason: str) -> CancellationDisposition:
        _text(reason, "Claude cancellation reason")
        with self._condition:
            if self._result or self._publishing:
                return CancellationDisposition.TOO_LATE
            if self._cancelled:
                return CancellationDisposition.ALREADY_REQUESTED
            self._cancelled = True
        try:
            self.inv.attachment.cancel(reason)
        except Exception:
            pass
        return CancellationDisposition.REQUESTED

    def current(self) -> bool:
        with self._condition:
            return not self._cancelled

    def claim(self) -> str | None:
        with self._condition:
            if self._cancelled:
                return "cancelled"
            grant = self.inv.attachment.grants().current()
            if grant is None or grant.grant_epoch != self.inv.grant_epoch:
                return "grant-mismatch"
            if self.adapter._clock() >= min(self.inv.attachment.deadline, grant.deadline):
                return "deadline-exceeded"
            binding = self.inv.attachment.binding
            if not isinstance(binding, MotusAttachmentBinding):
                return "runtime-local-lease-required"
            try:
                observed = binding.provider.lookup(binding.lease_identity.operation_id)
            except Exception:
                return "runtime-local-lease-required"
            if (
                observed is None
                or observed.identity != binding.lease_identity
                or observed.state is not LeaseState.READY
            ):
                return "runtime-local-lease-required"
            self._publishing = True
            return None

    def close(self) -> RuntimeOperationCleanup:
        with self._condition:
            if self._closed:
                return self._closed
            if self._result is None and not self._cancelled:
                raise RuntimeProtocolError("operation-active")
        self._thread.join(self.adapter._config.disconnect_timeout + self.adapter._config.cancellation_grace)
        disposition = self._cleanup if not self._thread.is_alive() else RuntimeCleanupDisposition.UNVERIFIED
        self._closed = RuntimeOperationCleanup(
            self.operation_id,
            disposition,
            "client-not-created"
            if disposition is RuntimeCleanupDisposition.NOT_CREATED
            else "client-closed"
            if disposition is RuntimeCleanupDisposition.CLEAN
            else "cleanup-uncertain",
        )
        return self._closed


class ClaudeRuntimeAdapter:
    descriptor, program, continuation_descriptor, territory = (
        CLAUDE_A2_LOCAL,
        CLAUDE_PROGRAM,
        CLAUDE_CONTINUATION_DESCRIPTOR,
        CLAUDE_LOCAL_TERRITORY,
    )

    def __init__(
        self,
        config: ClaudeRuntimeConfig,
        codec: ClaudeContinuationCodec,
        turns: ClaudeTurnOperations,
        custody: ClaudeConnectionCustody,
        *,
        clock: Callable[[], float] = time.monotonic,
        client_factory: _ClientFactory | None = None,
    ) -> None:
        if (
            not isinstance(config, ClaudeRuntimeConfig)
            or not isinstance(codec, ClaudeContinuationCodec)
            or not isinstance(turns, ClaudeTurnOperations)
            or not isinstance(custody, ClaudeConnectionCustody)
        ):
            raise TypeError("Claude adapter requires exact config, codec, turn custody, and connection custody")
        self._config, self._codec, self._turns, self._custody, self._clock, self._factory = (
            config,
            codec,
            turns,
            custody,
            clock,
            client_factory,
        )
        self._installation: RuntimeInstallation | None = None
        self._cli: str | None = None
        self._operations: dict[str, _Operation] = {}
        self._lock = threading.RLock()

    def __repr__(self) -> str:
        return f"ClaudeRuntimeAdapter(model={self._config.model!r}, ready={self._installation is not None!r})"

    def probe(self, *, cli_path: str | None = None) -> RuntimeProbeResult:
        try:
            version = importlib.metadata.version("claude-agent-sdk")
        except importlib.metadata.PackageNotFoundError:
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.NOT_INSTALLED,
                    issues=(ProbeIssue("sdk-not-installed", "claude-agent-sdk"),),
                ),
                None,
            )
        try:
            sdk = importlib.import_module("claude_agent_sdk")
        except Exception:
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.UNAVAILABLE,
                    issues=(ProbeIssue("sdk-unavailable", "claude-agent-sdk"),),
                ),
                None,
            )
        cli = cli_path or _bundled_cli(sdk) or shutil.which("claude")
        if cli is None:
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.NOT_INSTALLED,
                    issues=(ProbeIssue("client-not-installed", "claude"),),
                ),
                None,
            )
        try:
            output = subprocess.run(
                (cli, "--version"), capture_output=True, text=True, check=True, timeout=10
            ).stdout.strip()
        except OSError, subprocess.SubprocessError:
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.UNAVAILABLE,
                    issues=(ProbeIssue("client-unavailable", "claude"),),
                ),
                None,
            )
        match = re.search(r"(?<![0-9])([0-9]+\.[0-9]+\.[0-9]+)(?![0-9])", output)
        cli_version = match.group(1) if match else "unparseable"
        installation = RuntimeInstallation(
            self.descriptor.identity,
            1,
            (
                InstalledComponent("claude-agent-sdk", version, CLAUDE_SDK_SOURCE),
                InstalledComponent("claude-code", cli_version, CLAUDE_CODE_SOURCE),
            ),
            platform.system().lower() or "unknown",
            platform.machine().lower() or "unknown",
            frozenset({"runtime.cancel", "runtime.continue", "runtime.local", "runtime.provider-managed"}),
        )
        if version != CLAUDE_SDK_VERSION or cli_version != CLAUDE_CODE_VERSION:
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.INCOMPATIBLE,
                    installation,
                    (ProbeIssue("version-mismatch", "claude"),),
                ),
                None,
            )
        required = (
            "ClaudeSDKClient",
            "ClaudeAgentOptions",
            "ResultMessage",
            "MirrorErrorMessage",
            "UserMessage",
            "AssistantMessage",
            "SystemMessage",
            "StreamEvent",
            "RateLimitEvent",
            "SessionStore",
            "tool",
            "create_sdk_mcp_server",
            "HookMatcher",
        )
        option_fields = {
            "tools",
            "allowed_tools",
            "mcp_servers",
            "strict_mcp_config",
            "permission_mode",
            "resume",
            "session_store",
            "session_store_flush",
            "setting_sources",
            "skills",
            "plugins",
            "agents",
            "model",
            "fallback_model",
            "cwd",
            "cli_path",
            "env",
            "max_turns",
            "max_budget_usd",
            "max_buffer_size",
            "hooks",
            "stderr",
        }
        if any(not hasattr(sdk, name) for name in required) or not option_fields <= set(
            inspect.signature(sdk.ClaudeAgentOptions).parameters
        ):
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.UNAVAILABLE,
                    installation,
                    (ProbeIssue("protocol-unavailable", "claude-agent-sdk"),),
                ),
                None,
            )
        self._factory = self._factory or _OfficialFactory(sdk)
        return self._record(
            RuntimeProbeResult(self.descriptor.identity, ProbeDisposition.READY, installation), os.path.abspath(cli)
        )

    def _record(self, result: RuntimeProbeResult, cli: str | None) -> RuntimeProbeResult:
        self._installation = result.installation if result.disposition is ProbeDisposition.READY else None
        self._cli = cli if self._installation else None
        return result

    def start(self, inv: ClaudeRuntimeInvocation) -> RuntimeOperation:
        if not isinstance(inv, ClaudeRuntimeInvocation):
            raise TypeError("Claude runtime requires ClaudeRuntimeInvocation")
        if self._installation is None or self._cli is None or self._factory is None:
            raise RuntimeProtocolError("runtime-not-ready")
        self._validate(inv)
        if inv.continuation and inv.continuation.state is not ContinuationState.IN_USE:
            raise RuntimeProtocolError("continuation-not-claimed")
        prior = self._codec.load(inv.continuation) if inv.continuation else None
        if prior is not None and prior.project_binding != _project_binding(self._config.working_directory):
            raise RuntimeProtocolError("continuation-project-mismatch")
        coordinates = inv.attachment.coordinates()
        identity = (
            inv.episode_id.value,
            inv.turn_id.value,
            sha256(inv.prompt.encode()).hexdigest(),
            inv.connection.identity.connection_id,
            inv.connection.authority_epoch,
            inv.connection.state_version,
            coordinates.attachment_id,
            coordinates.attachment_epoch,
            inv.grant_epoch,
            self._config.model,
            inv.continuation.id.value if inv.continuation else None,
            inv.continuation.thread.value if inv.continuation else None,
            sha256(inv.continuation.state_reference.encode()).hexdigest() if inv.continuation else None,
            prior.session_id if prior else None,
            sha256(prior.transcript).hexdigest() if prior else None,
        )
        digest = sha256(repr(identity).encode()).hexdigest()
        key = _Key(digest)
        with self._lock:
            old = self._operations.get(inv.operation_id)
            if old:
                if old.key != key:
                    raise RuntimeProtocolError("operation-conflict")
                return old
            operation = _Operation(self, inv, key, prior, self._factory)
            self._operations[inv.operation_id] = operation
        try:
            operation.start()
        except Exception:
            with self._lock:
                self._operations.pop(inv.operation_id, None)
            raise
        return operation

    def _validate(self, inv: ClaudeRuntimeInvocation) -> None:
        expected = {
            DescriptorKind.RUNTIME: self.descriptor.identity,
            DescriptorKind.CONNECTION: _CONNECTION_ID,
            DescriptorKind.PROGRAM: _PROGRAM_ID,
            DescriptorKind.HANDS: _HANDS_ID,
            DescriptorKind.TERRITORY: _TERRITORY_ID,
            DescriptorKind.CONTINUATION: _CONTINUATION_ID,
        }
        if any((d := inv.attachment.snapshot.descriptor(k)) is None or d.identity != v for k, v in expected.items()):
            raise RuntimeProtocolError("resolution-mismatch")
        effect = inv.attachment.snapshot.descriptor(DescriptorKind.EFFECT)
        if effect is None or "effect.host-fenced" not in effect.offers:
            raise RuntimeProtocolError("resolution-mismatch")
        grant = inv.attachment.grants().current()
        if grant is None or grant.grant_epoch != inv.grant_epoch:
            raise RuntimeProtocolError("grant-mismatch")
        binding = inv.attachment.binding
        if (
            not isinstance(binding, MotusAttachmentBinding)
            or binding.execution.lease.state is not LeaseState.READY
            or binding.execution.lease.provider != "local-process"
        ):
            raise RuntimeProtocolError("runtime-local-lease-required")
        try:
            observed = binding.provider.lookup(binding.lease_identity.operation_id)
        except Exception:
            raise RuntimeProtocolError("runtime-local-lease-required") from None
        if observed is None or observed.identity != binding.lease_identity or observed.state is not LeaseState.READY:
            raise RuntimeProtocolError("runtime-local-lease-required")

    def _settle(
        self,
        inv: ClaudeRuntimeInvocation,
        outcome: TurnOutcome,
        appends: int,
        code: str,
        output: str | None = None,
        continuation: str | None = None,
    ) -> RuntimeTurnSettlement:
        return RuntimeTurnSettlement(inv.episode_id, inv.turn_id, outcome, appends, code, output, continuation)

    async def _execute(  # noqa: C901 - fail-closed cleanup and publication precedence is intentionally explicit
        self, operation: _Operation, factory: _ClientFactory
    ) -> tuple[RuntimeTurnSettlement, RuntimeCleanupDisposition]:
        inv, prior = operation.inv, operation.prior
        materialization: Materialization | None = None
        client: _Client | None = None
        root: Path | None = None
        root_identity: tuple[int, int] | None = None
        materialization_attempted = False
        clean = True
        outcome, code = TurnOutcome.FAILED, "runtime-failed"
        appends = 0
        output_reference = continuation_reference = None
        store = _SessionStore(
            max_entries=self._config.max_messages,
            max_total_bytes=self._config.max_transcript_bytes,
            project_key=prior.project_key if prior else None,
            session_id=prior.session_id if prior else None,
        )
        loop = asyncio.get_running_loop()
        hard_deadline = loop.time() + min(
            self._config.wall_timeout,
            max(0.0, inv.attachment.deadline - self._clock()),
        )
        ids = {name: f"{inv.operation_id}.{name}" for name in ("materialize", "admit", "release")}

        def remaining() -> float:
            value = hard_deadline - loop.time()
            if value <= 0:
                raise RuntimeProtocolError("deadline-exceeded")
            return value

        try:
            if prior is not None:
                store.seed(prior.transcript)
            if not operation.current():
                raise RuntimeProtocolError("cancelled")
            ttl = min(self._config.credential_ttl, remaining())
            materialization_attempted = True
            materialization = self._custody.materialize(
                inv.connection.identity.connection_id,
                self._config.host_id,
                mode=LeaseMode.READ,
                ttl=ttl,
                operation_id=ids["materialize"],
            )
            if not isinstance(materialization, Materialization) or materialization.mode is not LeaseMode.READ:
                raise RuntimeProtocolError("custody-materialization-mismatch")
            fence = materialization.fence
            if (
                not isinstance(fence, AttachmentFence)
                or fence.connection_id != inv.connection.identity.connection_id
                or fence.host_id != self._config.host_id
                or fence.authority_epoch != inv.connection.authority_epoch
                or fence.base_version != inv.connection.state_version
            ):
                raise RuntimeProtocolError("custody-state-mismatch")
            if not operation.current():
                raise RuntimeProtocolError("cancelled")
            credential = materialization.home.read()
            if not isinstance(credential, bytes) or not credential or len(credential) > 8192:
                raise RuntimeProtocolError("credential-invalid")
            try:
                api_key = credential.decode("utf-8", "strict")
                _text(api_key, "Claude credential", 8192)
            except UnicodeDecodeError, ValueError:
                raise RuntimeProtocolError("credential-invalid") from None

            root = Path(mkdtemp(prefix="operation-", dir=self._config.runtime_root))
            os.chmod(root, 0o700)
            root_metadata = root.lstat()
            if (
                root.is_symlink()
                or not root.is_dir()
                or (root_metadata.st_mode & 0o777) != 0o700
                or root_metadata.st_uid != os.geteuid()
            ):
                raise RuntimeProtocolError("private-root-invalid")
            root_identity = (root_metadata.st_dev, root_metadata.st_ino)
            cli = self._cli
            if cli is None:
                raise RuntimeProtocolError("runtime-not-ready")
            cli_wrapper = _install_cli_wrapper(root, cli)
            environment = dict(_AUTH_ENVIRONMENT)
            environment.update({"ANTHROPIC_API_KEY": api_key, "CLAUDE_CONFIG_DIR": str(root)})
            options: dict[str, object] = {
                "tools": list(_TOOLS),
                "allowed_tools": list(_TOOLS),
                "strict_mcp_config": True,
                "permission_mode": "dontAsk",
                "setting_sources": [],
                "skills": [],
                "plugins": [],
                "agents": {},
                "model": self._config.model,
                "fallback_model": None,
                "cwd": self._config.working_directory,
                "cli_path": cli_wrapper,
                "env": environment,
                "max_turns": self._config.max_turns,
                "max_budget_usd": self._config.max_budget_usd,
                "max_buffer_size": self._config.max_message_bytes,
                "session_store": store,
                "session_store_flush": "eager",
                "resume": prior.session_id if prior else None,
                "stderr": _discard_provider_stderr,
            }
            client = factory.create(options, inv.gateway, inv)
            operation._client = client
            await asyncio.wait_for(client.connect(), timeout=remaining())
            if not operation.current():
                raise RuntimeProtocolError("cancelled")
            await asyncio.wait_for(client.query(inv.prompt), timeout=remaining())
            events = await self._drain(operation, client, hard_deadline)
            await asyncio.wait_for(client.disconnect(), timeout=self._config.disconnect_timeout)
            client = None
            operation._client = None
            mirror = any(isinstance(event, _MirrorError) for event in events)
            results = [event for event in events if isinstance(event, _Result)]
            if mirror or store.failed:
                raise RuntimeProtocolError("session-store-failed")
            if len(results) != 1:
                raise RuntimeProtocolError("result-cardinality")
            result = results[0]
            session = _uuid(result.session_id)
            if prior is not None and session != prior.session_id:
                raise RuntimeProtocolError("session-mismatch")
            project_key, transcript = store.snapshot(session)
            if not operation.current():
                raise RuntimeProtocolError("cancelled")
            if result.subtype != "success" or result.is_error or result.terminal_reason != "completed":
                code = "provider-failed"
            else:
                publication_error = operation.claim()
                if publication_error is not None:
                    raise RuntimeProtocolError(publication_error)
                admission = self._custody.admit_result(fence, operation_id=ids["admit"])
                if (
                    not isinstance(admission, AdmissionResult)
                    or admission.operation_id != ids["admit"]
                    or admission.purpose != "result"
                    or admission.attachment_id != fence.attachment_id
                ):
                    raise RuntimeProtocolError("custody-admission-mismatch")
                text = _sanitize(result.text, self._config.max_message_bytes)
                stored_output = _text(
                    self._turns.store_turn(inv.operation_id, text),
                    "Claude output reference",
                    512,
                )
                stored_continuation = self._codec.store(
                    inv.operation_id,
                    ClaudeContinuationPayloadV1(
                        session,
                        _project_binding(self._config.working_directory),
                        project_key,
                        transcript,
                    ),
                )
                output_reference, continuation_reference = stored_output, stored_continuation
                outcome, code, appends = TurnOutcome.COMPLETED, "turn-completed", 1
        except RuntimeProtocolError as error:
            code = error.code
            outcome = TurnOutcome.CANCELLED if code == "cancelled" or not operation.current() else TurnOutcome.FAILED
            if outcome is TurnOutcome.CANCELLED:
                code = "cancelled"
        except asyncio.TimeoutError:
            code = "deadline-exceeded"
            outcome = TurnOutcome.CANCELLED if not operation.current() else TurnOutcome.FAILED
            if outcome is TurnOutcome.CANCELLED:
                code = "cancelled"
        except Exception:
            code = "provider-failed"
            outcome = TurnOutcome.CANCELLED if not operation.current() else TurnOutcome.FAILED
            if outcome is TurnOutcome.CANCELLED:
                code = "cancelled"
        finally:
            if client is not None:
                try:
                    await asyncio.wait_for(client.disconnect(), self._config.disconnect_timeout)
                except Exception:
                    clean = False
            operation._client = None
            if root is not None:
                clean = _remove_private_root(root, root_identity) and clean
            if materialization is not None:
                try:
                    release = self._custody.release(materialization, operation_id=ids["release"])
                    clean = (
                        _connection_release_verified(release, ids["release"], materialization.fence.attachment_id)
                        and clean
                    )
                except Exception:
                    clean = False

        if not clean:
            return self._settle(inv, TurnOutcome.FAILED, 0, "cleanup-unverified"), RuntimeCleanupDisposition.UNVERIFIED
        cleanup = (
            RuntimeCleanupDisposition.CLEAN if materialization_attempted else RuntimeCleanupDisposition.NOT_CREATED
        )
        return (
            self._settle(inv, outcome, appends, code, output_reference, continuation_reference),
            cleanup,
        )

    async def _drain(  # noqa: C901 - the interrupt/result race is intentionally one state surface
        self,
        operation: _Operation,
        client: _Client,
        hard_deadline: float,
    ) -> tuple[object, ...]:
        events: list[object] = []
        total_bytes = 0

        async def receive() -> None:
            nonlocal total_bytes
            async for event in client.receive_response():
                if not isinstance(event, _Result | _MirrorError | _Event):
                    raise RuntimeProtocolError("malformed-message")
                if type(event.encoded_size) is not int or event.encoded_size < 0:
                    raise RuntimeProtocolError("malformed-message")
                if event.encoded_size > self._config.max_message_bytes:
                    raise RuntimeProtocolError("message-overflow")
                total_bytes += event.encoded_size
                if len(events) >= self._config.max_messages or total_bytes > self._config.max_transcript_bytes:
                    raise RuntimeProtocolError("message-overflow")
                events.append(event)

        task = asyncio.create_task(receive())
        interrupted = False
        stop_code: str | None = None
        grace_deadline: float | None = None
        loop = asyncio.get_running_loop()
        try:
            while not task.done():
                if stop_code is None:
                    if not operation.current():
                        stop_code = "cancelled"
                    elif loop.time() >= hard_deadline:
                        stop_code = "deadline-exceeded"
                if stop_code is not None and not interrupted:
                    try:
                        await asyncio.wait_for(asyncio.shield(client.interrupt()), self._config.cancellation_grace)
                    except Exception:
                        raise RuntimeProtocolError("interrupt-failed") from None
                    interrupted = True
                    grace_deadline = loop.time() + self._config.cancellation_grace
                if grace_deadline is not None and loop.time() >= grace_deadline:
                    raise RuntimeProtocolError(stop_code or "deadline-exceeded")
                timeout = 0.05
                if stop_code is None:
                    timeout = min(timeout, max(0.001, hard_deadline - loop.time()))
                elif grace_deadline is not None:
                    timeout = min(timeout, max(0.001, grace_deadline - loop.time()))
                await asyncio.wait({task}, timeout=timeout)
            await task
            if stop_code is not None:
                raise RuntimeProtocolError(stop_code)
            return tuple(events)
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task


def _sanitize(value: object, maximum: int) -> str:
    if not isinstance(value, str):
        raise RuntimeProtocolError("malformed-result")
    sanitized = _ANSI_ESCAPE.sub("", value)
    sanitized = "".join(
        character if character in "\n\r\t" or (32 <= ord(character) and not 127 <= ord(character) <= 159) else "�"
        for character in sanitized
    )
    if len(sanitized.encode()) > maximum:
        raise RuntimeProtocolError("result-overflow")
    return sanitized


def _discard_provider_stderr(_line: str) -> None:
    return None


def _install_cli_wrapper(root: Path, cli: str) -> str:
    path = root / "claude-launcher"
    source = f"""#!{sys.executable} -I
import os
import sys

source = os.environ
home = source.get("CLAUDE_CONFIG_DIR", {str(root)!r})
environment = {{
    "HOME": home,
    "PATH": os.defpath,
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
}}
for name in (
    "ANTHROPIC_API_KEY",
    "CLAUDE_CONFIG_DIR",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_AGENT_SDK_VERSION",
):
    if name in source:
        environment[name] = source[name]
target = {cli!r}
os.execve(target, [target, *sys.argv[1:]], environment)
""".encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o700)
    try:
        remaining = memoryview(source)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise RuntimeProtocolError("private-root-invalid")
            remaining = remaining[written:]
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
            or (metadata.st_mode & 0o777) != 0o700
        ):
            raise RuntimeProtocolError("private-root-invalid")
    finally:
        os.close(descriptor)
    return str(path)


def _project_binding(path: Path) -> str:
    return sha256(str(path).encode()).hexdigest()


def _connection_release_verified(value: object, operation_id: str, attachment_id: str) -> bool:
    if not isinstance(value, ReleaseResult) or value.operation_id != operation_id:
        return False
    cleanup = value.cleanup
    return (
        isinstance(cleanup, CleanupEvidence)
        and cleanup.attachment_id == attachment_id
        and (cleanup.removed or cleanup.already_absent)
        and not cleanup.security_violation
    )


def _remove_private_root(path: Path, identity: tuple[int, int] | None) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return True
    if (
        path.is_symlink()
        or not path.is_dir()
        or metadata.st_uid != os.geteuid()
        or (metadata.st_mode & 0o777) != 0o700
        or (identity is not None and (metadata.st_dev, metadata.st_ino) != identity)
    ):
        return False
    try:
        shutil.rmtree(path)
    except OSError:
        return False
    return not os.path.lexists(path)


def _bundled_cli(sdk: object) -> str | None:
    try:
        source = getattr(sdk, "__file__", None)
        if not isinstance(source, str):
            return None
        root = Path(source).resolve().parent
        candidates = (root / "_bundled" / "claude", root / "_bundled" / "claude.exe")
        return next((str(path) for path in candidates if path.is_file()), None)
    except Exception:
        return None


__all__ = [
    "CLAUDE_CODE_DISTRIBUTION_COMMIT",
    "CLAUDE_CODE_VERSION",
    "CLAUDE_COLLOCATED_HANDS",
    "CLAUDE_CONNECTION_CAPABILITIES",
    "CLAUDE_CONTINUATION_CAPABILITIES",
    "CLAUDE_CONTINUATION_DESCRIPTOR",
    "CLAUDE_LOCAL_TERRITORY",
    "CLAUDE_PROGRAM",
    "CLAUDE_PROGRAM_CAPABILITIES",
    "CLAUDE_SDK_SOURCE_COMMIT",
    "CLAUDE_SDK_VERSION",
    "ClaudeConnectionCustody",
    "ClaudeContinuationCodec",
    "ClaudeContinuationOperations",
    "ClaudeContinuationPayloadV1",
    "ClaudeRuntimeAdapter",
    "ClaudeRuntimeConfig",
    "ClaudeRuntimeInvocation",
    "ClaudeTurnOperations",
]
