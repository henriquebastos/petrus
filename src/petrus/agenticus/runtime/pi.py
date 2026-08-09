"""Exact Pi 0.83.0 native A2/A4 runtime over a private JSONL Node bridge."""

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
from uuid import UUID, uuid4

from petrus.agenticus.attachment.binding import MotusAttachmentBinding
from petrus.agenticus.attachment.episode import EpisodeAttachment
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorIdentity, DescriptorKind
from petrus.agenticus.connection.custody import (
    AdmissionResult,
    AttachmentFence,
    CleanupEvidence,
    ConnectionIdentity,
    ConnectionStatus,
    ConnectionView,
    LeaseMode,
    Materialization,
    PublicationResult,
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
from petrus.agenticus.runtime.profiles import PI_NATIVE_A2_LOCAL, PI_NATIVE_A4_E2B, PI_NATIVE_A4_GONDOLIN
from petrus.agenticus.runtime.result import RuntimeTurnSettlement
from petrus.agenticus.thread.continuation import Continuation, ContinuationDescriptor, ContinuationState
from petrus.agenticus.thread.identity import EpisodeId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome
from petrus.motus.execution import LeaseState

PI_SDK_VERSION = "0.83.0"
PI_SDK_SOURCE_COMMIT = "6e48c10f5b1f5cfc90d6cb21abf26a3e1e8a6bd7"
PI_AI_VERSION = "0.83.0"
PI_SOURCE_COMMIT = PI_SDK_SOURCE_COMMIT
PI_SDK_SOURCE = f"npm:@earendil-works/pi-coding-agent@{PI_SDK_VERSION}#commit={PI_SDK_SOURCE_COMMIT}"
PI_AI_SOURCE = f"npm:@earendil-works/pi-ai@{PI_AI_VERSION}#commit={PI_SOURCE_COMMIT}"
PI_CC_PATCH_VERSION = "1.0.1"
PI_CC_PATCH_SOURCE_COMMIT = "1891a39e3e1c61e37f950159fdc51de1ecffce84"
PI_CC_PATCH_SOURCE = (
    "npm:pi-cc-patch@1.0.1#"
    "sha512-1yxwj/4K3RIT+zAcngpL6yQ3QHwYDx6oJ+F7vQU4SHGotspqexPfSTxlSgzdtVD35jrqbTSeccwQrE5cjdVXlg=="
)
PI_API_KEY_CATALOG = (
    ("anthropic", "claude-sonnet-4-5"),
    ("openrouter", "anthropic/claude-sonnet-4.5"),
    ("openai", "gpt-5.6-sol"),
)
PI_SUBSCRIPTION_CATALOG = (
    ("anthropic", "claude-sonnet-4-5"),
    ("openai-codex", "gpt-5.6-sol"),
)
PI_CC_PATCH_SUBSCRIPTION_CATALOG = (("anthropic", "claude-sonnet-4-5"),)

_PROGRAM_ID = DescriptorIdentity(DescriptorKind.PROGRAM, "pi.harness-owned", 1)
_CONTINUATION_ID = DescriptorIdentity(DescriptorKind.CONTINUATION, "pi.native", 1)
_CONNECTION_ID = DescriptorIdentity(DescriptorKind.CONNECTION, "pi.compatible-api-key", 1)
_SUBSCRIPTION_CONNECTION_ID = DescriptorIdentity(DescriptorKind.CONNECTION, "pi.native-subscription", 1)
_CC_PATCH_CONNECTION_ID = DescriptorIdentity(DescriptorKind.CONNECTION, "pi.cc-patch-subscription", 1)
_HANDS_ID = DescriptorIdentity(DescriptorKind.HANDS, "pi.collocated", 1)
_CAPABILITY_HANDS_ID = DescriptorIdentity(DescriptorKind.HANDS, "pi.capability-scoped", 1)
_TERRITORY_ID = DescriptorIdentity(DescriptorKind.TERRITORY, "motus.local", 1)
_GONDOLIN_TERRITORY_ID = DescriptorIdentity(DescriptorKind.TERRITORY, "motus.gondolin", 1)
_E2B_TERRITORY_ID = DescriptorIdentity(DescriptorKind.TERRITORY, "motus.e2b", 1)
PI_CONTINUATION_DESCRIPTOR = ContinuationDescriptor(_CONTINUATION_ID, _PROGRAM_ID)
PI_PROGRAM = AgentProgramDescriptor(
    identity=_PROGRAM_ID,
    ownership=ProgramOwnership.HARNESS,
    accepted_continuations=(ContinuationRequirement(_CONTINUATION_ID, _PROGRAM_ID),),
    produced_continuation=_CONTINUATION_ID,
    owns_steering=False,
    owns_evaluation=False,
)
PI_PROGRAM_CAPABILITIES = CapabilityDescriptor(_PROGRAM_ID, frozenset({"program.harness-owned"}))
PI_CONTINUATION_CAPABILITIES = CapabilityDescriptor(_CONTINUATION_ID, frozenset({"continuation.pi-native"}))
PI_CONNECTION_CAPABILITIES = CapabilityDescriptor(_CONNECTION_ID, frozenset({"connection.pi-compatible"}))
PI_SUBSCRIPTION_CONNECTION_CAPABILITIES = CapabilityDescriptor(
    _SUBSCRIPTION_CONNECTION_ID, frozenset({"connection.pi-compatible"})
)
PI_CC_PATCH_CONNECTION_CAPABILITIES = CapabilityDescriptor(
    _CC_PATCH_CONNECTION_ID, frozenset({"connection.pi-compatible"})
)
PI_COLLOCATED_HANDS = CapabilityDescriptor(_HANDS_ID, frozenset({"hands.collocated"}))
PI_CAPABILITY_SCOPED_HANDS = CapabilityDescriptor(_CAPABILITY_HANDS_ID, frozenset({"hands.capability-scoped"}))
PI_LOCAL_TERRITORY = CapabilityDescriptor(_TERRITORY_ID, frozenset())
PI_GONDOLIN_TERRITORY = CapabilityDescriptor(_GONDOLIN_TERRITORY_ID, frozenset())
PI_E2B_TERRITORY = CapabilityDescriptor(_E2B_TERRITORY_ID, frozenset())

_MAX_PROMPT = 64 * 1024
_MAX_KEY = 8192
_MAX_AUTH = 1_000_000
_DEFAULT_SESSION = 4_000_000
_HELPER_FRAME_LIMIT = 16 * 1024 * 1024
_CC_PATCH_INDEX_SHA256 = "a2829f6fd8c5f9b12b2297ba2edc4b4b8b80b4d676adcd65a88855e72d76729a"
_PUBLICATION_MARGIN = 5.0
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
_METHODS = tuple(method.value for method in ToolMethod)
_SCHEMAS: dict[str, dict[str, object]] = {
    ToolMethod.WORKSPACE_READ.value: {
        "type": "object",
        "properties": {"path": {"type": "string", "minLength": 1, "maxLength": MAX_PATH_CHARS}},
        "required": ["path"],
        "additionalProperties": False,
    },
    ToolMethod.WORKSPACE_SEARCH.value: {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": MAX_QUERY_CHARS},
            "path": {"type": "string", "minLength": 1, "maxLength": MAX_PATH_CHARS},
        },
        "required": ["query", "path"],
        "additionalProperties": False,
    },
    ToolMethod.WORKSPACE_SHELL.value: {
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
    ToolMethod.WORKSPACE_WRITE.value: {
        "type": "object",
        "properties": {
            "path": {"type": "string", "minLength": 1, "maxLength": MAX_PATH_CHARS},
            "content": {"type": "string", "maxLength": MAX_CONTENT_CHARS},
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    },
    ToolMethod.WORKSPACE_TEST.value: {"type": "object", "properties": {}, "additionalProperties": False},
}


def _text(value: object, label: str, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > maximum
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError(f"{label} must be bounded non-empty text")
    return value


def _uuid(value: object) -> str:
    value = _text(value, "Pi session identity", 36)
    try:
        parsed = UUID(value)
    except ValueError, AttributeError:
        raise ValueError("Pi session identity must be canonical") from None
    if str(parsed) != value or _UUID.fullmatch(value) is None:
        raise ValueError("Pi session identity must be canonical")
    return value


def _strict_load(data: bytes) -> object:
    def reject(_: str) -> object:
        raise ValueError

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError
            value[key] = item
        return value

    return json.loads(data.decode("utf-8", "strict"), parse_constant=reject, object_pairs_hook=unique)


def _validate_native_auth(value: bytes, provider: str, maximum: int) -> bytes:
    if not value or len(value) > maximum or value.decode("utf-8", "strict").encode() != value:
        raise ValueError
    stored = _strict_load(value)
    if type(stored) is not dict or set(stored) != {provider}:
        raise ValueError
    credential = cast(dict[str, object], stored)[provider]
    if type(credential) is not dict:
        raise ValueError
    credential = cast(dict[str, object], credential)
    expires = credential.get("expires")
    if (
        credential.get("type") != "oauth"
        or not isinstance(credential.get("access"), str)
        or not credential["access"]
        or not isinstance(credential.get("refresh"), str)
        or not credential["refresh"]
        or isinstance(expires, bool)
        or not isinstance(expires, int | float)
        or not math.isfinite(expires)
        or (
            provider == "openai-codex"
            and (not isinstance(credential.get("accountId"), str) or not credential["accountId"])
        )
    ):
        raise ValueError
    return value


def _decode_native_auth(value: object, provider: str, maximum: int) -> bytes:
    if not isinstance(value, str):
        raise ValueError
    body = base64.b64decode(value, validate=True)
    if base64.b64encode(body).decode() != value:
        raise ValueError
    return _validate_native_auth(body, provider, maximum)


def _validate_session(value: object, session_id: str, maximum: int = _DEFAULT_SESSION, events: int = 10_000) -> bytes:
    if not isinstance(value, bytes) or not value or len(value) > maximum or not value.endswith(b"\n"):
        raise ValueError("Pi session must be bounded complete JSONL")
    lines = value.splitlines(keepends=True)
    if not lines or len(lines) > events:
        raise ValueError("Pi session event bound exceeded")
    objects: list[dict[str, object]] = []
    try:
        for line in lines:
            if not line.endswith(b"\n") or line in (b"\n", b"\r\n"):
                raise ValueError
            item = _strict_load(line[:-1] if line[-1:] == b"\n" else line)
            if type(item) is not dict:
                raise ValueError
            objects.append(cast(dict[str, object], item))
    except UnicodeDecodeError, json.JSONDecodeError, ValueError:
        raise ValueError("Pi session must contain strict JSON objects") from None
    headers = [entry for entry in objects if entry.get("type") == "session"]
    header = objects[0]
    if (
        len(headers) != 1
        or header.get("type") != "session"
        or header.get("version") != 3
        or header.get("id") != session_id
    ):
        raise ValueError("Pi session header mismatch")
    return value


@dataclass(frozen=True)
class PiContinuationPayloadV1:
    session_id: str = field(repr=False)
    working_directory_binding: str = field(repr=False)
    session_jsonl: bytes = field(repr=False)
    schema_version: int = field(default=1, init=False)

    def __post_init__(self) -> None:
        session_id = _uuid(self.session_id)
        object.__setattr__(self, "session_id", session_id)
        binding = _text(self.working_directory_binding, "Pi working-directory binding", 64)
        if re.fullmatch(r"[0-9a-f]{64}", binding) is None:
            raise ValueError("Pi working-directory binding must be SHA-256")
        object.__setattr__(self, "working_directory_binding", binding)
        _validate_session(self.session_jsonl, session_id)


@runtime_checkable
class PiContinuationOperations(Protocol):
    def store(self, operation_id: str, payload: PiContinuationPayloadV1) -> str: ...
    def load(self, state_reference: str) -> PiContinuationPayloadV1: ...


@runtime_checkable
class PiTurnOperations(Protocol):
    def store_turn(self, operation_id: str, final_text: str) -> str: ...


class PiContinuationCodec:
    descriptor = PI_CONTINUATION_DESCRIPTOR

    def __init__(self, operations: PiContinuationOperations) -> None:
        if not isinstance(operations, PiContinuationOperations):
            raise TypeError("Pi codec requires PiContinuationOperations")
        self._operations = operations

    def store(self, operation_id: str, payload: PiContinuationPayloadV1) -> str:
        return _text(self._operations.store(_text(operation_id, "Pi operation"), payload), "state reference", 512)

    def load(self, continuation: Continuation) -> PiContinuationPayloadV1:
        if not isinstance(continuation, Continuation) or continuation.descriptor != self.descriptor:
            raise ValueError("Pi Continuation does not match this runtime")
        value = self._operations.load(continuation.state_reference)
        if not isinstance(value, PiContinuationPayloadV1):
            raise TypeError("Pi custody returned a foreign payload")
        return value


@dataclass(frozen=True)
class PiRuntimeConfig:
    provider: str
    model: str
    working_directory: Path = field(repr=False)
    runtime_root: Path = field(repr=False)
    host_id: str = "local"
    cc_patch: bool = False
    credential_ttl: float = 315.0
    wall_timeout: float = 300.0
    cancellation_grace: float = 2.0
    max_events: int = 10_000
    max_tool_calls: int = 256
    max_frame_bytes: int = 14 * 1024 * 1024
    max_output_bytes: int = 1_000_000
    max_session_bytes: int = _DEFAULT_SESSION
    max_auth_bytes: int = _MAX_AUTH
    territory_profile: str = "local"

    def __post_init__(self) -> None:  # noqa: C901 - validates independent security bounds
        for name in ("provider", "model", "host_id"):
            object.__setattr__(self, name, _text(getattr(self, name), f"Pi {name}"))
        for name in ("working_directory", "runtime_root"):
            selected = Path(getattr(self, name))
            if selected.is_symlink():
                raise ValueError(f"Pi {name} must be stable")
            path = selected.resolve()
            if not path.is_dir():
                raise ValueError(f"Pi {name} must be an existing directory")
            metadata = path.stat()
            if name == "runtime_root" and (stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.geteuid()):
                raise ValueError("Pi runtime_root must be owned mode-0700")
            object.__setattr__(self, name, path)
        for name in ("credential_ttl", "wall_timeout", "cancellation_grace"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Pi {name} must be positive and finite")
        if not isinstance(self.cc_patch, bool):
            raise TypeError("Pi cc_patch must be boolean")
        if self.cc_patch and dict(PI_CC_PATCH_SUBSCRIPTION_CATALOG).get(self.provider) != self.model:
            raise ValueError("Pi cc_patch requires its exact Anthropic subscription pair")
        if not isinstance(self.territory_profile, str) or self.territory_profile not in {"local", "gondolin", "e2b"}:
            raise ValueError("Pi territory_profile must be local, gondolin, or e2b")
        for name in (
            "max_events",
            "max_tool_calls",
            "max_frame_bytes",
            "max_output_bytes",
            "max_session_bytes",
            "max_auth_bytes",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"Pi {name} must be positive")
        encoded_session = ((self.max_session_bytes + 2) // 3) * 4
        encoded_auth = ((self.max_auth_bytes + 2) // 3) * 4
        if (
            self.max_frame_bytes < encoded_session + encoded_auth + 6 * self.max_output_bytes + 128 * 1024
            or self.max_frame_bytes > _HELPER_FRAME_LIMIT
        ):
            raise ValueError("Pi frame bound cannot carry the output, session, and authority bounds")


@dataclass(frozen=True)
class PiRuntimeInvocation:
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
        object.__setattr__(self, "operation_id", _text(self.operation_id, "Pi operation"))
        if not isinstance(self.episode_id, EpisodeId) or not isinstance(self.turn_id, TurnId):
            raise TypeError("Pi invocation requires exact identities")
        if (
            not isinstance(self.prompt, str)
            or not self.prompt
            or len(self.prompt.encode()) > _MAX_PROMPT
            or "\0" in self.prompt
        ):
            raise ValueError("Pi prompt must be bounded non-empty text")
        if (
            not isinstance(self.connection, ConnectionView)
            or self.connection.status is not ConnectionStatus.READY
            or self.connection.identity.profile not in {"api-key", "subscription", "cc-patch-subscription"}
        ):
            raise ValueError("Pi invocation requires a ready compatible connection")
        catalog = (
            PI_CC_PATCH_SUBSCRIPTION_CATALOG
            if self.connection.identity.profile == "cc-patch-subscription"
            else PI_SUBSCRIPTION_CATALOG
        )
        if self.connection.identity.profile != "api-key" and self.connection.identity.provider not in dict(catalog):
            raise ValueError("Pi subscription connection requires an exact native OAuth provider")
        if not isinstance(self.attachment, EpisodeAttachment) or self.attachment.episode_id != self.episode_id:
            raise ValueError("Pi invocation requires its exact attachment")
        if not isinstance(self.gateway, HandsGateway):
            raise TypeError("Pi invocation requires HandsGateway")
        c = self.attachment.coordinates()
        if (self.gateway.episode_id, self.gateway.attachment_id, self.gateway.attachment_epoch) != (
            c.episode_id,
            c.attachment_id,
            c.attachment_epoch,
        ):
            raise ValueError("Pi gateway attachment mismatch")
        if type(self.grant_epoch) is not int or self.grant_epoch <= 0:
            raise ValueError("Pi grant epoch must be positive")
        if self.continuation is not None and not isinstance(self.continuation, Continuation):
            raise TypeError("Pi continuation must be Continuation or None")


def pi_durable_work_fingerprint(
    config: PiRuntimeConfig,
    episode_id: EpisodeId,
    turn_id: TurnId,
    prompt: str,
    connection: ConnectionIdentity,
    continuation: Continuation | None = None,
) -> str:
    """Hash the stable, secret-free identity of prospective Pi work.

    This primitive deliberately needs no materialized connection, attachment,
    grant, or other process-scoped fence, so a host can check durable replay
    before allocating any of them.
    """
    if type(config) is not PiRuntimeConfig:
        raise TypeError("Pi durable fingerprint requires exact Pi runtime config")
    if not isinstance(episode_id, EpisodeId) or not isinstance(turn_id, TurnId):
        raise TypeError("Pi durable fingerprint requires exact identities")
    if not isinstance(connection, ConnectionIdentity):
        raise TypeError("Pi durable fingerprint requires ConnectionIdentity")
    if not isinstance(prompt, str) or not prompt or len(prompt.encode()) > _MAX_PROMPT or "\0" in prompt:
        raise ValueError("Pi prompt must be bounded non-empty text")
    if continuation is not None and not isinstance(continuation, Continuation):
        raise TypeError("Pi continuation must be Continuation or None")
    identity = {
        "schema_version": 1,
        "episode_id": episode_id.value,
        "turn_id": turn_id.value,
        "prompt_sha256": sha256(prompt.encode()).hexdigest(),
        "connection_id": connection.connection_id,
        "connection_provider": connection.provider,
        "connection_profile": connection.profile,
        "connection_account": connection.account_fingerprint,
        "provider": config.provider,
        "model": config.model,
        "territory": config.territory_profile,
        "cc_patch": config.cc_patch,
        "continuation": None
        if continuation is None
        else {
            "id": continuation.id.value,
            "thread": continuation.thread.value,
            "state_reference_sha256": sha256(continuation.state_reference.encode()).hexdigest(),
        },
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return sha256(encoded).hexdigest()


def pi_durable_fingerprint(config: PiRuntimeConfig, inv: PiRuntimeInvocation) -> str:
    """Hash an invocation by delegating to the prospective-work primitive."""
    if type(inv) is not PiRuntimeInvocation:
        raise TypeError("Pi durable fingerprint requires exact Pi runtime values")
    return pi_durable_work_fingerprint(
        config,
        inv.episode_id,
        inv.turn_id,
        inv.prompt,
        inv.connection.identity,
        inv.continuation,
    )


@dataclass(frozen=True)
class _Candidate:
    session_id: str
    text: str = field(repr=False)
    session_jsonl: bytes = field(repr=False)


@dataclass(frozen=True)
class _HelperResult:
    candidate: _Candidate | None
    native_auth: bytes | None = field(repr=False)
    code: str


class _HelperClient(Protocol):
    def run(
        self, gateway: HandsGateway, invocation: PiRuntimeInvocation, current: Callable[[], bool], deadline: float
    ) -> _HelperResult: ...
    def close(self) -> bool: ...


class _HelperFactory(Protocol):
    def create(
        self,
        *,
        node: str,
        sdk_entrypoint: str,
        private_root: Path,
        config: PiRuntimeConfig,
        invocation: PiRuntimeInvocation,
        prior: PiContinuationPayloadV1 | None,
        api_key: str | None,
        native_auth: bytes | None,
        extension: str | None,
    ) -> _HelperClient: ...


class _SubprocessFactory:
    def __init__(self, helper: Path) -> None:
        self._helper = helper

    def create(
        self,
        *,
        node: str,
        sdk_entrypoint: str,
        private_root: Path,
        config: PiRuntimeConfig,
        invocation: PiRuntimeInvocation,
        prior: PiContinuationPayloadV1 | None,
        api_key: str | None,
        native_auth: bytes | None,
        extension: str | None,
    ) -> _HelperClient:
        return _SubprocessClient(
            node=node,
            sdk_entrypoint=sdk_entrypoint,
            helper=self._helper,
            private_root=private_root,
            config=config,
            invocation=invocation,
            prior=prior,
            api_key=api_key,
            native_auth=native_auth,
            extension=extension,
        )


class _SubprocessClient:
    def __init__(
        self,
        *,
        node: str,
        sdk_entrypoint: str,
        helper: Path,
        private_root: Path,
        config: PiRuntimeConfig,
        invocation: PiRuntimeInvocation,
        prior: PiContinuationPayloadV1 | None,
        api_key: str | None,
        native_auth: bytes | None,
        extension: str | None,
    ) -> None:
        self._config, self._inv, self._prior = config, invocation, prior
        if (api_key is None) == (native_auth is None):
            raise RuntimeProtocolError("credential-invalid")
        env = {"HOME": str(private_root), "PATH": str(Path(node).parent), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        try:
            self._process = subprocess.Popen(
                (node, str(helper), sdk_entrypoint, extension or "--no-extension"),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                start_new_session=True,
                bufsize=0,
            )
        except OSError:
            raise RuntimeProtocolError("helper-launch-failed") from None
        self._stderr = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr.start()
        self._closed = False
        session_id = prior.session_id if prior else str(uuid4())
        self._start: dict[str, object] = {
            "type": "start",
            "version": 1,
            "provider": config.provider,
            "model": config.model,
            "prompt": invocation.prompt,
            "cwd": str(config.working_directory),
            "root": str(private_root),
            "session_id": session_id,
            "session": base64.b64encode(prior.session_jsonl).decode() if prior else None,
            "schemas": _SCHEMAS,
            "limits": {
                "frame": config.max_frame_bytes,
                "output": config.max_output_bytes,
                "session": config.max_session_bytes,
                "events": config.max_events,
                "tools": config.max_tool_calls,
            },
        }
        if api_key is not None:
            self._start["api_key"] = api_key
        else:
            assert native_auth is not None
            self._start["auth"] = base64.b64encode(native_auth).decode()
            cast(dict[str, object], self._start["limits"])["auth"] = config.max_auth_bytes

    def _drain_stderr(self) -> None:
        stream = self._process.stderr
        if stream is not None:
            while stream.read(65536):
                pass

    def _write(self, frame: dict[str, object]) -> None:
        stream = self._process.stdin
        if stream is None:
            raise RuntimeProtocolError("helper-pipe-failed")
        try:
            encoded = json.dumps(frame, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode() + b"\n"
            if len(encoded) > self._config.max_frame_bytes:
                raise RuntimeProtocolError("frame-overflow")
            stream.write(encoded)
            stream.flush()
        except OSError, ValueError:
            raise RuntimeProtocolError("helper-pipe-failed") from None

    def run(  # noqa: C901 - protocol state machine is intentionally one fail-closed surface
        self, gateway: HandsGateway, invocation: PiRuntimeInvocation, current: Callable[[], bool], deadline: float
    ) -> _HelperResult:
        self._write(self._start)
        subscription = "auth" in self._start
        selector = selectors.DefaultSelector()
        stdout = self._process.stdout
        if stdout is None:
            raise RuntimeProtocolError("helper-pipe-failed")
        selector.register(stdout, selectors.EVENT_READ)
        buffer = bytearray()
        ready = terminal = abort_sent = False
        seen: set[str] = set()
        events = tools = 0
        grace_end = 0.0
        candidate: _Candidate | None = None
        native_auth: bytes | None = None
        terminal_code: str | None = None
        try:
            while terminal is False:
                now = time.monotonic()
                stopping = not current() or now >= deadline
                if stopping and not abort_sent:
                    self._write({"type": "abort"})
                    abort_sent, grace_end = True, now + self._config.cancellation_grace
                if abort_sent and now >= grace_end:
                    raise RuntimeProtocolError("cancelled" if not current() else "deadline-exceeded")
                if self._process.poll() is not None and not selector.select(0):
                    break
                for key, _ in selector.select(0.05):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(stdout)
                        continue
                    buffer.extend(chunk)
                    if len(buffer) > self._config.max_frame_bytes:
                        raise RuntimeProtocolError("frame-overflow")
                    while b"\n" in buffer:
                        raw, _, rest = buffer.partition(b"\n")
                        buffer = bytearray(rest)
                        try:
                            frame = _strict_load(bytes(raw))
                        except ValueError, UnicodeDecodeError, json.JSONDecodeError:
                            raise RuntimeProtocolError("malformed-frame") from None
                        if type(frame) is not dict:
                            raise RuntimeProtocolError("malformed-frame")
                        frame = cast(dict[str, object], frame)
                        events += 1
                        if events > self._config.max_events:
                            raise RuntimeProtocolError("event-overflow")
                        kind = frame.get("type")
                        if kind == "ready":
                            if ready or terminal or set(frame) != {"type"}:
                                raise RuntimeProtocolError("frame-order")
                            ready = True
                        elif kind == "tool_call":
                            if not ready or terminal or set(frame) != {"type", "id", "method", "params"}:
                                raise RuntimeProtocolError("frame-order")
                            identity, method, params = frame["id"], frame["method"], frame["params"]
                            encoded = json.dumps(params, separators=(",", ":"), allow_nan=False).encode()
                            if (
                                not isinstance(identity, str)
                                or not identity
                                or len(identity.encode()) > 128
                                or identity in seen
                                or method not in _METHODS
                                or type(params) is not dict
                                or len(encoded) > 8192
                            ):
                                raise RuntimeProtocolError("malformed-tool-call")
                            tools += 1
                            if tools > self._config.max_tool_calls:
                                raise RuntimeProtocolError("tool-overflow")
                            seen.add(identity)
                            c = invocation.attachment.coordinates()
                            result = gateway.submit(
                                {
                                    "version": 1,
                                    "call_id": identity,
                                    "episode_id": c.episode_id,
                                    "attachment_id": c.attachment_id,
                                    "attachment_epoch": c.attachment_epoch,
                                    "grant_epoch": invocation.grant_epoch,
                                    "method": method,
                                    "params": params,
                                }
                            )
                            self._write({"type": "tool_result", "id": identity, "result": result.to_model_data()})
                        elif kind == "complete":
                            expected = {"type", "session_id", "text", "session", *(("auth",) if subscription else ())}
                            if not ready or terminal or set(frame) != expected:
                                raise RuntimeProtocolError("frame-order")
                            try:
                                sid = _uuid(frame["session_id"])
                                text = frame["text"]
                                if not isinstance(text, str) or len(text.encode()) > self._config.max_output_bytes:
                                    raise ValueError
                                encoded_session = frame["session"]
                                if not isinstance(encoded_session, str):
                                    raise ValueError
                                body = base64.b64decode(encoded_session, validate=True)
                                _validate_session(body, sid, self._config.max_session_bytes, self._config.max_events)
                                native_auth = (
                                    _decode_native_auth(
                                        frame["auth"], self._config.provider, self._config.max_auth_bytes
                                    )
                                    if subscription
                                    else None
                                )
                            except TypeError, ValueError:
                                raise RuntimeProtocolError("malformed-complete") from None
                            candidate, terminal = _Candidate(sid, text, body), True
                        elif kind == "failed":
                            provider_failure = frame.get("code") == "provider-failed"
                            expected = {"type", "code", *(("auth",) if subscription and provider_failure else ())}
                            if (
                                terminal
                                or set(frame) != expected
                                or frame.get("code")
                                not in {"aborted", "provider-failed", "session-invalid", "protocol-failed"}
                            ):
                                raise RuntimeProtocolError("malformed-failed")
                            terminal = True
                            terminal_code = str(frame["code"])
                            if subscription and provider_failure:
                                try:
                                    native_auth = _decode_native_auth(
                                        frame["auth"], self._config.provider, self._config.max_auth_bytes
                                    )
                                except TypeError, ValueError:
                                    raise RuntimeProtocolError("malformed-failed") from None
                            if terminal_code == "aborted" and abort_sent:
                                terminal_code = "cancelled" if not current() else "deadline-exceeded"
                        else:
                            raise RuntimeProtocolError("unknown-frame")
            if buffer or not terminal or (candidate is None) == (terminal_code is None):
                raise RuntimeProtocolError("terminal-missing")
            if self._prior and candidate is not None and candidate.session_id != self._prior.session_id:
                raise RuntimeProtocolError("session-mismatch")
            try:
                returncode = self._process.wait(timeout=self._config.cancellation_grace)
            except subprocess.TimeoutExpired:
                raise RuntimeProtocolError("helper-exit-inconsistent") from None
            expected_returncode = 0 if candidate is not None else 1
            if returncode != expected_returncode:
                raise RuntimeProtocolError("helper-exit-inconsistent")
            if terminal_code is not None and not (subscription and terminal_code == "provider-failed"):
                raise RuntimeProtocolError(terminal_code)
            return _HelperResult(candidate, native_auth, terminal_code or "turn-completed")
        finally:
            selector.close()

    def close(self) -> bool:
        if self._closed:
            return self._process.poll() is not None
        self._closed = True
        for stream in (self._process.stdin, self._process.stdout):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        try:
            if self._process.poll() is None:
                try:
                    os.killpg(self._process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self._process.wait(timeout=self._config.cancellation_grace)
        except OSError, subprocess.TimeoutExpired:
            return False
        self._stderr.join(self._config.cancellation_grace)
        if self._process.stderr is not None:
            try:
                self._process.stderr.close()
            except OSError:
                pass
        return self._process.poll() is not None and not self._stderr.is_alive()


@runtime_checkable
class PiConnectionCustody(Protocol):
    def materialize(
        self, connection_id: str, host_id: str, *, mode: LeaseMode, ttl: float, operation_id: str
    ) -> Materialization: ...
    def activate(self, materialization: Materialization, *, operation_id: str) -> None: ...
    def admit_result(self, fence: AttachmentFence, *, operation_id: str) -> AdmissionResult: ...
    def checkpoint(self, materialization: Materialization, *, operation_id: str) -> PublicationResult: ...
    def release(self, materialization: Materialization, *, operation_id: str) -> ReleaseResult: ...


@dataclass(frozen=True)
class _Key:
    digest: str


class _Operation:
    def __init__(
        self,
        adapter: PiRuntimeAdapter,
        inv: PiRuntimeInvocation,
        key: _Key,
        prior: PiContinuationPayloadV1 | None,
        factory: _HelperFactory,
    ) -> None:
        self.adapter, self.inv, self.key, self.prior, self.factory = adapter, inv, key, prior, factory
        self._condition = threading.Condition()
        self._cancelled = self._publishing = False
        self._result: RuntimeTurnSettlement | None = None
        self._cleanup_disposition = RuntimeCleanupDisposition.UNVERIFIED
        self._cleanup: RuntimeOperationCleanup | None = None
        self._thread = threading.Thread(target=self._run, name=f"pi-{key.digest[:12]}", daemon=True)

    @property
    def operation_id(self) -> str:
        return self.inv.operation_id

    @property
    def closed(self) -> bool:
        with self._condition:
            return self._cleanup is not None

    def receipt(self) -> RuntimeTurnSettlement | None:
        with self._condition:
            return self._result

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        try:
            result, cleanup = self.adapter._execute(self, self.factory)
        except BaseException:
            result = self.adapter._settle(self.inv, TurnOutcome.FAILED, 0, "runtime-failed")
            cleanup = RuntimeCleanupDisposition.UNVERIFIED
        with self._condition:
            if self._cancelled and result.outcome is not TurnOutcome.CANCELLED:
                result = self.adapter._settle(self.inv, TurnOutcome.CANCELLED, 0, "cancelled")
            self._result, self._cleanup_disposition = result, cleanup
            self._condition.notify_all()

    def current(self) -> bool:
        with self._condition:
            return not self._cancelled

    def _publication_error(self) -> str | None:
        if self._cancelled:
            return "cancelled"
        grant = self.inv.attachment.grants().current()
        if grant is None or grant.grant_epoch != self.inv.grant_epoch:
            return "grant-mismatch"
        if self.adapter._clock() >= min(grant.deadline, self.inv.attachment.deadline):
            return "deadline-exceeded"
        return None

    def claim(self) -> str | None:
        with self._condition:
            if error := self._publication_error():
                return error
        binding_current = self.adapter._binding_current(self.inv)
        with self._condition:
            if error := self._publication_error():
                return error
            if not binding_current:
                return self.adapter._lease_failure
            self._publishing = True
            return None

    def wait(self, timeout: float | None = None) -> RuntimeTurnSettlement:
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("Pi wait timeout must be positive and finite")
        with self._condition:
            if self._cleanup is not None:
                raise RuntimeProtocolError("operation-closed")
            self._condition.wait_for(lambda: self._result is not None, timeout)
            if self._result is None:
                raise TimeoutError("Pi operation has not settled")
            return self._result

    def cancel(self, reason: str) -> CancellationDisposition:
        _text(reason, "Pi cancellation reason")
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


class PiRuntimeAdapter:
    program, continuation_descriptor = PI_PROGRAM, PI_CONTINUATION_DESCRIPTOR

    def __init__(
        self,
        config: PiRuntimeConfig,
        codec: PiContinuationCodec,
        turns: PiTurnOperations,
        custody: PiConnectionCustody,
        *,
        clock: Callable[[], float] = time.monotonic,
        client_factory: _HelperFactory | None = None,
    ) -> None:
        if (
            not isinstance(config, PiRuntimeConfig)
            or not isinstance(codec, PiContinuationCodec)
            or not isinstance(turns, PiTurnOperations)
            or not isinstance(custody, PiConnectionCustody)
        ):
            raise TypeError("Pi adapter requires exact collaborators")
        self._config, self._codec, self._turns, self._custody, self._clock = config, codec, turns, custody, clock
        self.descriptor, self.hands, self.territory = {
            "local": (PI_NATIVE_A2_LOCAL, PI_COLLOCATED_HANDS, PI_LOCAL_TERRITORY),
            "gondolin": (PI_NATIVE_A4_GONDOLIN, PI_CAPABILITY_SCOPED_HANDS, PI_GONDOLIN_TERRITORY),
            "e2b": (PI_NATIVE_A4_E2B, PI_CAPABILITY_SCOPED_HANDS, PI_E2B_TERRITORY),
        }[config.territory_profile]
        split = config.territory_profile != "local"
        self._runtime_capabilities = frozenset(
            {
                "runtime.cancel",
                "runtime.continue",
                "runtime.harness-owned",
                "runtime.split" if split else "runtime.local",
            }
        )
        self._lease_provider = "local-process" if config.territory_profile == "local" else config.territory_profile
        self._lease_failure = "runtime-territory-lease-required" if split else "runtime-local-lease-required"
        self._factory = client_factory
        self._installation: RuntimeInstallation | None = None
        self._node = self._sdk_entrypoint = None
        self._cc_patch_entrypoint: str | None = None
        self._helper: Path | None = None
        self._operations: dict[str, _Operation] = {}
        self._lock = threading.RLock()

    def __repr__(self) -> str:
        return f"PiRuntimeAdapter(territory_profile={self._config.territory_profile!r}, provider={self._config.provider!r}, model={self._config.model!r}, ready={self._installation is not None!r})"

    @property
    def config(self) -> PiRuntimeConfig:
        return self._config

    def probe(  # noqa: C901 - exact package and extension probe is one fail-closed boundary
        self,
        *,
        cli_path: str | None = None,
        node_path: str | None = None,
        package_root: str | None = None,
        cc_patch_root: str | None = None,
    ) -> RuntimeProbeResult:
        cli, node = cli_path or shutil.which("pi"), node_path or shutil.which("node")
        if cli is None or node is None:
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.NOT_INSTALLED,
                    issues=(ProbeIssue("client-not-installed" if cli is None else "node-not-installed", "pi"),),
                )
            )
        try:
            cli_real, node_real = Path(cli).resolve(strict=True), Path(node).resolve(strict=True)
            root = Path(package_root).resolve(strict=True) if package_root else cli_real.parent.parent
            if cli_real != (root / "dist/cli.js").resolve(strict=True):
                raise ValueError
            package = json.loads((root / "package.json").read_text())
            sdk = (root / "dist/index.js").resolve(strict=True)
            nested_ai = root / "node_modules" / "@earendil-works" / "pi-ai"
            ai_root = (nested_ai if nested_ai.is_dir() else root.parent / "pi-ai").resolve(strict=True)
            ai = json.loads((ai_root / "package.json").read_text())
            dependency = package.get("dependencies", {}).get("@earendil-works/pi-ai")
            if (
                package.get("name") != "@earendil-works/pi-coding-agent"
                or package.get("version") != PI_SDK_VERSION
                or package.get("bin") not in ({"pi": "dist/cli.js"}, "dist/cli.js")
                or package.get("main") not in ("dist/index.js", "./dist/index.js")
                or ai.get("name") != "@earendil-works/pi-ai"
                or ai.get("version") != PI_AI_VERSION
                or dependency not in (PI_AI_VERSION, f"^{PI_AI_VERSION}", f"~{PI_AI_VERSION}")
            ):
                raise ValueError
            version = subprocess.run(
                (str(node_real), "--version"), capture_output=True, text=True, check=True, timeout=10
            ).stdout.strip()
            match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", version)
            if match is None or tuple(map(int, match.groups())) < (22, 19, 0):
                raise ValueError
            cc_patch_entrypoint: Path | None = None
            if self._config.cc_patch:
                cc_root = (
                    Path(cc_patch_root).resolve(strict=True)
                    if cc_patch_root
                    else (root.parent.parent / "pi-cc-patch").resolve(strict=True)
                )
                cc_package = json.loads((cc_root / "package.json").read_text())
                cc_patch_entrypoint = (cc_root / "index.ts").resolve(strict=True)
                if (
                    cc_package.get("name") != "pi-cc-patch"
                    or cc_package.get("version") != PI_CC_PATCH_VERSION
                    or cc_package.get("pi") != {"extensions": ["./index.ts"]}
                    or sha256(cc_patch_entrypoint.read_bytes()).hexdigest() != _CC_PATCH_INDEX_SHA256
                ):
                    raise ValueError
            helper = Path(__file__).with_name("pi_helper.mjs").resolve(strict=True)
            catalogs = {
                "api_keys": PI_API_KEY_CATALOG,
                "subscriptions": PI_SUBSCRIPTION_CATALOG,
                "cc_patch_subscriptions": PI_CC_PATCH_SUBSCRIPTION_CATALOG,
            }
            probe = subprocess.run(
                (
                    str(node_real),
                    str(helper),
                    str(sdk),
                    "--probe",
                    json.dumps(catalogs, separators=(",", ":")),
                    *((str(cc_patch_entrypoint),) if cc_patch_entrypoint else ()),
                ),
                capture_output=True,
                check=False,
                timeout=10,
                env={"HOME": os.devnull, "PATH": str(node_real.parent), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
            )
            frame = _strict_load(probe.stdout.rstrip(b"\n"))
            if (
                probe.returncode
                or probe.stderr
                or probe.stdout.count(b"\n") != 1
                or frame != {"type": "probe", "ok": True}
            ):
                raise ValueError
        except OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError:
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.UNAVAILABLE,
                    issues=(ProbeIssue("protocol-unavailable", "pi"),),
                )
            )
        components = [
            InstalledComponent("pi-coding-agent", PI_SDK_VERSION, PI_SDK_SOURCE),
            InstalledComponent("pi-ai", PI_AI_VERSION, PI_AI_SOURCE),
            InstalledComponent("node", version[1:], f"executable:{node_real}"),
        ]
        if cc_patch_entrypoint is not None:
            components.append(InstalledComponent("pi-cc-patch", PI_CC_PATCH_VERSION, PI_CC_PATCH_SOURCE))
        installation = RuntimeInstallation(
            self.descriptor.identity,
            1,
            tuple(components),
            platform.system().lower() or "unknown",
            platform.machine().lower() or "unknown",
            self._runtime_capabilities,
        )
        with self._lock:
            self._node, self._sdk_entrypoint, self._helper = str(node_real), str(sdk), helper
            self._cc_patch_entrypoint = str(cc_patch_entrypoint) if cc_patch_entrypoint else None
            if self._factory is None:
                self._factory = _SubprocessFactory(helper)
        return self._record(RuntimeProbeResult(self.descriptor.identity, ProbeDisposition.READY, installation))

    def _record(self, result: RuntimeProbeResult) -> RuntimeProbeResult:
        with self._lock:
            self._installation = result.installation if result.disposition is ProbeDisposition.READY else None
            if self._installation is None:
                self._node = self._sdk_entrypoint = None
                self._cc_patch_entrypoint = None
                self._helper = None
                if isinstance(self._factory, _SubprocessFactory):
                    self._factory = None
        return result

    def start(self, inv: PiRuntimeInvocation) -> RuntimeOperation:
        if not isinstance(inv, PiRuntimeInvocation):
            raise TypeError("Pi runtime requires PiRuntimeInvocation")
        self._validate(inv)
        if inv.continuation and inv.continuation.state is not ContinuationState.IN_USE:
            raise RuntimeProtocolError("continuation-not-claimed")
        prior = self._codec.load(inv.continuation) if inv.continuation else None
        if prior and prior.working_directory_binding != _working_binding(self._config.working_directory):
            raise RuntimeProtocolError("continuation-project-mismatch")
        c = inv.attachment.coordinates()
        identity = (
            inv.episode_id.value,
            inv.turn_id.value,
            sha256(inv.prompt.encode()).hexdigest(),
            inv.connection.identity.connection_id,
            inv.connection.authority_epoch,
            inv.connection.state_version,
            c.attachment_id,
            c.attachment_epoch,
            inv.grant_epoch,
            self._config.provider,
            self._config.model,
            self._config.territory_profile,
            inv.continuation.id.value if inv.continuation else None,
            inv.continuation.thread.value if inv.continuation else None,
            sha256(inv.continuation.state_reference.encode()).hexdigest() if inv.continuation else None,
            prior.session_id if prior else None,
            sha256(prior.session_jsonl).hexdigest() if prior else None,
        )
        key = _Key(sha256(repr(identity).encode()).hexdigest())
        with self._lock:
            if (
                self._installation is None
                or self._factory is None
                or self._node is None
                or self._sdk_entrypoint is None
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

    def evict(self, operation_id: str) -> bool:
        """Remove one closed process-local receipt without changing durable state."""
        operation_id = _text(operation_id, "Pi operation")
        with self._lock:
            operation = self._operations.get(operation_id)
            if operation is None:
                return False
            if not operation.closed:
                raise RuntimeProtocolError("operation-active")
            del self._operations[operation_id]
            return True

    def receipt(self, operation_id: str) -> RuntimeTurnSettlement | None:
        """Return one secret-free local settlement without changing handle state."""
        operation_id = _text(operation_id, "Pi operation")
        with self._lock:
            operation = self._operations.get(operation_id)
            return None if operation is None else operation.receipt()

    def _validate(self, inv: PiRuntimeInvocation) -> None:
        self._validate_connection(inv)
        connection = (
            _CC_PATCH_CONNECTION_ID
            if inv.connection.identity.profile == "cc-patch-subscription"
            else _SUBSCRIPTION_CONNECTION_ID
            if inv.connection.identity.profile == "subscription"
            else _CONNECTION_ID
        )
        expected = {
            DescriptorKind.RUNTIME: self.descriptor.identity,
            DescriptorKind.CONNECTION: connection,
            DescriptorKind.PROGRAM: _PROGRAM_ID,
            DescriptorKind.HANDS: self.hands.identity,
            DescriptorKind.TERRITORY: self.territory.identity,
            DescriptorKind.CONTINUATION: _CONTINUATION_ID,
        }
        if any((d := inv.attachment.snapshot.descriptor(k)) is None or d.identity != v for k, v in expected.items()):
            raise RuntimeProtocolError("resolution-mismatch")
        effect = inv.attachment.snapshot.descriptor(DescriptorKind.EFFECT)
        grant = inv.attachment.grants().current()
        if effect is None or "effect.host-fenced" not in effect.offers:
            raise RuntimeProtocolError("resolution-mismatch")
        if grant is None or grant.grant_epoch != inv.grant_epoch:
            raise RuntimeProtocolError("grant-mismatch")
        if not self._binding_current(inv):
            raise RuntimeProtocolError(self._lease_failure)

    def _binding_current(self, inv: PiRuntimeInvocation) -> bool:
        binding = inv.attachment.binding
        if (
            not isinstance(binding, MotusAttachmentBinding)
            or binding.execution.lease.state is not LeaseState.READY
            or binding.execution.lease.provider != self._lease_provider
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
            and observed.provider == self._lease_provider
        )

    def _validate_connection(self, inv: PiRuntimeInvocation) -> None:
        if inv.connection.identity.provider != self._config.provider:
            raise RuntimeProtocolError("connection-provider-mismatch")
        profile = inv.connection.identity.profile
        if self._config.cc_patch != (profile == "cc-patch-subscription"):
            raise RuntimeProtocolError("connection-profile-mismatch")
        if self._config.cc_patch and self._cc_patch_entrypoint is None:
            raise RuntimeProtocolError("cc-patch-not-ready")
        if profile != "api-key":
            catalog = PI_CC_PATCH_SUBSCRIPTION_CATALOG if self._config.cc_patch else PI_SUBSCRIPTION_CATALOG
            if dict(catalog).get(self._config.provider) != self._config.model:
                raise RuntimeProtocolError("subscription-model-mismatch")
            reserve = _PUBLICATION_MARGIN + 2 * self._config.cancellation_grace
            if self._config.credential_ttl < self._config.wall_timeout + reserve:
                raise RuntimeProtocolError("subscription-ttl-insufficient")

    def _settle(
        self,
        inv: PiRuntimeInvocation,
        outcome: TurnOutcome,
        appends: int,
        code: str,
        output: str | None = None,
        continuation: str | None = None,
    ) -> RuntimeTurnSettlement:
        return RuntimeTurnSettlement(inv.episode_id, inv.turn_id, outcome, appends, code, output, continuation)

    def _execute(  # noqa: C901 - cleanup and publication precedence remain explicit
        self, operation: _Operation, factory: _HelperFactory
    ) -> tuple[RuntimeTurnSettlement, RuntimeCleanupDisposition]:
        inv, prior = operation.inv, operation.prior
        subscription = inv.connection.identity.profile in {"subscription", "cc-patch-subscription"}
        materialization = None
        client = None
        root = None
        identity = None
        attempted = False
        connection_settled = False
        clean = True
        outcome, code = TurnOutcome.FAILED, "runtime-failed"
        output_ref = continuation_ref = None
        ids = {
            name: f"{inv.operation_id}.{name}" for name in ("materialize", "activate", "admit", "checkpoint", "release")
        }
        reserve = _PUBLICATION_MARGIN + 2 * self._config.cancellation_grace if subscription else 0.0
        attachment_remaining = max(0.0, inv.attachment.deadline - self._clock())
        run_budget = min(self._config.wall_timeout, max(0.0, attachment_remaining - reserve))
        deadline = time.monotonic() + run_budget
        try:
            if not operation.current():
                raise RuntimeProtocolError("cancelled")
            if run_budget <= 0 or self._clock() >= inv.attachment.deadline:
                raise RuntimeProtocolError("deadline-exceeded")
            attempted = True
            mode = LeaseMode.REFRESH if subscription else LeaseMode.READ
            materialization = self._custody.materialize(
                inv.connection.identity.connection_id,
                self._config.host_id,
                mode=mode,
                ttl=min(self._config.credential_ttl, max(0.001, run_budget + reserve)),
                operation_id=ids["materialize"],
            )
            if not isinstance(materialization, Materialization) or materialization.mode is not mode:
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
            maximum = self._config.max_auth_bytes if subscription else _MAX_KEY
            if not isinstance(credential, bytes) or not credential or len(credential) > maximum:
                raise RuntimeProtocolError("credential-invalid")
            api_key = None
            native_auth = credential if subscription else None
            if subscription:
                try:
                    _validate_native_auth(credential, self._config.provider, self._config.max_auth_bytes)
                except UnicodeDecodeError, json.JSONDecodeError, ValueError:
                    raise RuntimeProtocolError("credential-invalid") from None
            else:
                try:
                    api_key = credential.decode("utf-8", "strict")
                    _text(api_key, "Pi credential", _MAX_KEY)
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
            assert self._node and self._sdk_entrypoint
            client = factory.create(
                node=self._node,
                sdk_entrypoint=self._sdk_entrypoint,
                private_root=root,
                config=self._config,
                invocation=inv,
                prior=prior,
                api_key=api_key,
                native_auth=native_auth,
                extension=self._cc_patch_entrypoint if self._config.cc_patch else None,
            )
            if subscription:
                self._custody.activate(materialization, operation_id=ids["activate"])
            helper_result = client.run(inv.gateway, inv, operation.current, deadline)
            candidate = helper_result.candidate
            if subscription:
                if (
                    helper_result.native_auth is None
                    or (candidate is None and helper_result.code != "provider-failed")
                    or (candidate is not None and helper_result.code != "turn-completed")
                ):
                    raise RuntimeProtocolError("credential-invalid")
                try:
                    _validate_native_auth(
                        helper_result.native_auth,
                        self._config.provider,
                        self._config.max_auth_bytes,
                    )
                except UnicodeDecodeError, json.JSONDecodeError, ValueError:
                    raise RuntimeProtocolError("credential-invalid") from None
                clean = client.close() and clean
                client = None
                clean = _remove_root(root, identity) and clean
                root = None
                if not clean:
                    raise RuntimeProtocolError("private-cleanup-uncertain")
            elif candidate is None or helper_result.native_auth is not None or helper_result.code != "turn-completed":
                raise RuntimeProtocolError("malformed-complete")
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
            if subscription:
                assert helper_result.native_auth is not None
                materialization.home.replace(helper_result.native_auth)
                publication = self._custody.checkpoint(materialization, operation_id=ids["checkpoint"])
                connection_settled = _checkpoint_verified(
                    publication,
                    ids["checkpoint"],
                    materialization.fence.attachment_id,
                    inv,
                )
                if not connection_settled:
                    raise RuntimeProtocolError("connection-publication-mismatch")
            if candidate is not None:
                output_ref = _text(self._turns.store_turn(inv.operation_id, candidate.text), "Pi output reference", 512)
                continuation_ref = self._codec.store(
                    inv.operation_id,
                    PiContinuationPayloadV1(
                        candidate.session_id,
                        _working_binding(self._config.working_directory),
                        candidate.session_jsonl,
                    ),
                )
                outcome, code = TurnOutcome.COMPLETED, "turn-completed"
            else:
                outcome, code = TurnOutcome.FAILED, "provider-failed"
        except RuntimeProtocolError as error:
            code = error.code
            outcome = TurnOutcome.CANCELLED if not operation.current() or code == "cancelled" else TurnOutcome.FAILED
            if outcome is TurnOutcome.CANCELLED:
                code = "cancelled"
        except Exception:
            code = "runtime-failed"
            outcome = TurnOutcome.CANCELLED if not operation.current() else TurnOutcome.FAILED
        finally:
            if client is not None:
                clean = client.close() and clean
            if root is not None:
                clean = _remove_root(root, identity) and clean
            if materialization is not None and not connection_settled:
                try:
                    release = self._custody.release(materialization, operation_id=ids["release"])
                    clean = _release_verified(release, ids["release"], materialization.fence.attachment_id) and clean
                except Exception:
                    clean = False
        if not clean:
            return self._settle(inv, TurnOutcome.FAILED, 0, "cleanup-unverified"), RuntimeCleanupDisposition.UNVERIFIED
        if outcome is not TurnOutcome.COMPLETED:
            output_ref = continuation_ref = None
        return self._settle(
            inv, outcome, 1 if outcome is TurnOutcome.COMPLETED else 0, code, output_ref, continuation_ref
        ), RuntimeCleanupDisposition.CLEAN if attempted else RuntimeCleanupDisposition.NOT_CREATED


def _working_binding(path: Path) -> str:
    return sha256(str(path).encode()).hexdigest()


def _release_verified(value: object, operation_id: str, attachment_id: str) -> bool:
    return (
        isinstance(value, ReleaseResult)
        and value.operation_id == operation_id
        and isinstance(value.cleanup, CleanupEvidence)
        and value.cleanup.attachment_id == attachment_id
        and (value.cleanup.removed or value.cleanup.already_absent)
        and not value.cleanup.security_violation
    )


def _checkpoint_verified(
    value: object,
    operation_id: str,
    attachment_id: str,
    invocation: PiRuntimeInvocation,
) -> bool:
    return (
        isinstance(value, PublicationResult)
        and value.operation_id == operation_id
        and value.connection.identity == invocation.connection.identity
        and value.connection.status is ConnectionStatus.READY
        and value.connection.authority_epoch == invocation.connection.authority_epoch
        and value.connection.state_version == invocation.connection.state_version + 1
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
    "PI_API_KEY_CATALOG",
    "PI_AI_VERSION",
    "PI_CC_PATCH_CONNECTION_CAPABILITIES",
    "PI_CC_PATCH_SOURCE",
    "PI_CC_PATCH_SOURCE_COMMIT",
    "PI_CC_PATCH_SUBSCRIPTION_CATALOG",
    "PI_CC_PATCH_VERSION",
    "PI_SOURCE_COMMIT",
    "PI_CAPABILITY_SCOPED_HANDS",
    "PI_COLLOCATED_HANDS",
    "PI_CONNECTION_CAPABILITIES",
    "PI_CONTINUATION_CAPABILITIES",
    "PI_CONTINUATION_DESCRIPTOR",
    "PI_E2B_TERRITORY",
    "PI_GONDOLIN_TERRITORY",
    "PI_LOCAL_TERRITORY",
    "PI_PROGRAM",
    "PI_PROGRAM_CAPABILITIES",
    "PI_SDK_SOURCE_COMMIT",
    "PI_SDK_VERSION",
    "PI_SUBSCRIPTION_CATALOG",
    "PI_SUBSCRIPTION_CONNECTION_CAPABILITIES",
    "PiConnectionCustody",
    "PiContinuationCodec",
    "PiContinuationOperations",
    "PiContinuationPayloadV1",
    "PiRuntimeAdapter",
    "PiRuntimeConfig",
    "PiRuntimeInvocation",
    "PiTurnOperations",
    "pi_durable_fingerprint",
    "pi_durable_work_fingerprint",
]
