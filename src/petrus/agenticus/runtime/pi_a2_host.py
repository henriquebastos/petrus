"""Petrus-owned composition for one Pi A2 Local host lifecycle.

The host owns Agent Connection custody, the Motus territory, Episode
Attachment and Hands, native Continuation bodies, durable operation recovery,
and ordered teardown. The supported product surface is the explicitly scripted
runtime-conformance composition. Exact external Pi and provider execution
through ``compose_pi_a2_runtime`` remains experimental and qualification-only.
Probe and durable replay run before authority is requested.

The durable operation ledger is secret-free.  Provider output and native Pi
session JSONL live in a separate private body store and become loadable only
after aggregate runtime, Attachment, and territory cleanup is verified.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import stat
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol, cast

from petrus.agenticus.runtime import pi
from petrus.agenticus.attachment.binding import MotusAttachmentBinding
from petrus.agenticus.attachment.episode import EpisodeAttachment
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorIdentity, DescriptorKind
from petrus.agenticus.catalog.resolution import ResolutionSnapshot
from petrus.agenticus.connection.custody import (
    AgentConnectionCustody,
    ConnectionIdentity,
    ConnectionStatus,
    CustodyError,
    OpaqueState,
)
from petrus.agenticus.connection.key import KeyOperations
from petrus.agenticus.connection.materialization import PrivateFileMaterializer
from petrus.agenticus.connection.storage import SqliteConnectionStorage, StorageSecurityError
from petrus.agenticus.hands.contract import ToolMethod
from petrus.agenticus.hands.grants import CapabilityGrant
from petrus.agenticus.hands.workspace import STAGE_DIRECTORY, MotusWorkspaceAdapter
from petrus.agenticus.runtime.installation import ProbeDisposition, RuntimeProbeResult
from petrus.agenticus.runtime.operation import (
    RuntimeCleanupDisposition,
    RuntimeOperation,
    RuntimeOperationCleanup,
    RuntimeProtocolError,
)
from petrus.agenticus.runtime.pi import (
    PI_API_KEY_CATALOG,
    PI_COLLOCATED_HANDS,
    PI_CONNECTION_CAPABILITIES,
    PI_CONTINUATION_CAPABILITIES,
    PI_CONTINUATION_DESCRIPTOR,
    PI_LOCAL_TERRITORY,
    PI_PROGRAM_CAPABILITIES,
    PiContinuationCodec,
    PiContinuationOperations,
    PiContinuationPayloadV1,
    PiRuntimeAdapter,
    PiRuntimeConfig,
    PiRuntimeInvocation,
    PiTurnOperations,
    pi_durable_work_fingerprint,
)
from petrus.agenticus.runtime.pi_recovery import (
    PiOperationPhase,
    PiOperationRecord,
    SqlitePiOperationLedger,
)
from petrus.agenticus.runtime.profiles import PI_NATIVE_A2_LOCAL
from petrus.agenticus.runtime.result import RuntimeTurnSettlement
from petrus.agenticus.thread.continuation import Continuation, ContinuationState
from petrus.agenticus.thread.identity import EpisodeId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome
from petrus.motus.execution import EnvironmentCapability, EnvironmentProvider, EnvironmentSpec
from petrus.motus.execution.archive import validate_workspace_archive
from petrus.motus.execution.providers import LocalProcessEnvironment

_EFFECT = CapabilityDescriptor(
    DescriptorIdentity(DescriptorKind.EFFECT, "host.fenced", 1),
    frozenset({"effect.host-fenced"}),
)
_SNAPSHOT = ResolutionSnapshot(
    1,
    (
        PI_NATIVE_A2_LOCAL,
        PI_CONNECTION_CAPABILITIES,
        PI_PROGRAM_CAPABILITIES,
        PI_COLLOCATED_HANDS,
        PI_LOCAL_TERRITORY,
        PI_CONTINUATION_CAPABILITIES,
        _EFFECT,
    ),
)
_REQUIRED_INSTALLATION_CAPABILITIES = frozenset(
    {"runtime.cancel", "runtime.continue", "runtime.harness-owned", "runtime.local"}
)
_REQUIRED_ENVIRONMENT_CAPABILITIES = frozenset(
    {
        EnvironmentCapability.COMMAND_CANCELLATION.value,
        EnvironmentCapability.EXPLICIT_ENVIRONMENT.value,
        EnvironmentCapability.PRIVATE_FILE_TRANSFER.value,
        EnvironmentCapability.PROCESS_GROUP.value,
        EnvironmentCapability.WORKSPACE.value,
    }
)
_MAX_PROMPT_BYTES = 64 * 1024
_MAX_KEY_BYTES = 8192
_FINGERPRINT_SCHEMA_VERSION = 2
_SCRIPTED_SUPPORT_LABEL = "Pi A2 Local host lifecycle — scripted runtime conformance"
_SCRIPTED_SESSION = "00000000-0000-4000-8000-000000000001"


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


def _positive(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return float(value)


def _digest(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _private_root(path: Path) -> Path:
    selected = Path(path)
    if selected.is_symlink():
        raise StorageSecurityError("Pi A2 state root must not be a symlink")
    if not selected.exists():
        selected.mkdir(mode=0o700, parents=True)
        selected.chmod(0o700)
    resolved = selected.resolve()
    metadata = resolved.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.geteuid():
        raise StorageSecurityError("Pi A2 state root must be an owned mode-0700 directory")
    return resolved


def _private_subdirectory(root: Path, name: str) -> Path:
    selected = root / name
    if selected.is_symlink():
        raise StorageSecurityError(f"Pi A2 {name} root must not be a symlink")
    if not selected.exists():
        selected.mkdir(mode=0o700)
    metadata = selected.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.geteuid():
        raise StorageSecurityError(f"Pi A2 {name} root must be an owned mode-0700 directory")
    return selected


def _erase(buffer: bytearray) -> None:
    for index in range(len(buffer)):
        buffer[index] = 0


@dataclass(frozen=True)
class PiA2RuntimeHostConfig:
    """One explicit, finite, direct-API-key Pi A2 Local host profile.

    ``working_directory`` is stable native helper/session metadata. Episode
    workspace custody comes only from each :class:`PiA2RuntimeStart` archive.
    """

    state_root: Path = field(repr=False)
    working_directory: Path = field(repr=False)
    provider: str
    model: str
    host_id: str
    capabilities: frozenset[ToolMethod]
    allowed_argv: frozenset[tuple[str, ...]] = frozenset()
    test_command: tuple[str, ...] = ("/bin/true",)
    max_tool_calls: int = 16
    attachment_timeout: float = 960.0
    command_timeout: float = 60.0
    credential_ttl: float = 1_020.0
    wall_timeout: float = 900.0
    cancellation_grace: float = 5.0
    cli_path: str | None = field(default=None, repr=False)
    node_path: str | None = field(default=None, repr=False)
    package_root: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:  # noqa: C901 - one immutable fail-closed configuration boundary
        object.__setattr__(self, "provider", _text(self.provider, "Pi A2 provider"))
        object.__setattr__(self, "model", _text(self.model, "Pi A2 model"))
        object.__setattr__(self, "host_id", _text(self.host_id, "Pi A2 host"))
        if dict(PI_API_KEY_CATALOG).get(self.provider) != self.model:
            raise ValueError("Pi A2 host requires an exact direct API-key provider/model pair")
        working = Path(self.working_directory)
        if working.is_symlink():
            raise ValueError("Pi A2 working directory must be stable")
        working = working.resolve()
        if not working.is_dir():
            raise ValueError("Pi A2 working directory must be an existing directory")
        object.__setattr__(self, "working_directory", working)
        object.__setattr__(self, "state_root", Path(self.state_root))
        capabilities = frozenset(self.capabilities)
        if not capabilities or any(not isinstance(method, ToolMethod) for method in capabilities):
            raise TypeError("Pi A2 capabilities must contain exact ToolMethod values")
        object.__setattr__(self, "capabilities", capabilities)
        if type(self.max_tool_calls) is not int or self.max_tool_calls <= 0:
            raise ValueError("Pi A2 max_tool_calls must be positive")
        for name in (
            "attachment_timeout",
            "command_timeout",
            "credential_ttl",
            "wall_timeout",
            "cancellation_grace",
        ):
            object.__setattr__(self, name, _positive(getattr(self, name), f"Pi A2 {name}"))
        if self.attachment_timeout <= self.wall_timeout + self.cancellation_grace:
            raise ValueError("Pi A2 attachment timeout must exceed the runtime and cancellation bounds")
        command = tuple(self.test_command)
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("Pi A2 test command must be non-empty")
        object.__setattr__(self, "test_command", command)
        # Reuse the canonical grant validators before any Episode exists.
        if isinstance(self.allowed_argv, str):
            raise TypeError("Pi A2 argv policy must be a collection, not text")
        normalized = CapabilityGrant(
            "configuration",
            1,
            1,
            capabilities,
            frozenset(),
            frozenset(tuple(argv) for argv in self.allowed_argv),
            1.0,
            self.max_tool_calls,
        )
        object.__setattr__(self, "allowed_argv", normalized.allowed_argv)
        for name in ("cli_path", "node_path", "package_root"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _text(value, f"Pi A2 {name}", 4096))


@dataclass(frozen=True)
class PiA2RuntimePolicy:
    """One operation's exact attachment-scoped Hands authority."""

    capabilities: frozenset[ToolMethod]
    writable_paths: frozenset[str] = frozenset()
    max_tool_calls: int = 16
    writable_roots: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if isinstance(self.writable_paths, str) or isinstance(self.writable_roots, str):
            raise TypeError("Pi A2 writable path policy must use collections, not text")
        capabilities = frozenset(self.capabilities)
        if not capabilities or any(not isinstance(method, ToolMethod) for method in capabilities):
            raise TypeError("Pi A2 operation capabilities must contain exact ToolMethod values")
        normalized = CapabilityGrant(
            "operation-policy",
            1,
            1,
            capabilities,
            frozenset(self.writable_paths),
            frozenset(),
            1.0,
            self.max_tool_calls,
            writable_roots=frozenset(self.writable_roots),
            denied_writable_roots=frozenset({".git", STAGE_DIRECTORY}),
        )
        if (normalized.writable_paths or normalized.writable_roots) and ToolMethod.WORKSPACE_WRITE not in capabilities:
            raise ValueError("Pi A2 writable paths and roots require workspace-write capability")
        if any(
            path.split("/", 1)[0] in {".git", STAGE_DIRECTORY}
            for path in normalized.writable_paths | normalized.writable_roots
        ):
            raise ValueError("Pi A2 writable policy must exclude workspace control roots")
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "writable_paths", normalized.writable_paths)
        object.__setattr__(self, "writable_roots", normalized.writable_roots)


@dataclass(frozen=True)
class PiA2RuntimeStart:
    """Stable work identity, exact workspace, and bounded policy for one Pi operation."""

    operation_id: str
    episode_id: EpisodeId
    turn_id: TurnId
    prompt: str = field(repr=False)
    workspace_archive: bytes = field(repr=False)
    workspace_digest: str
    workspace_correlation: str
    policy: PiA2RuntimePolicy
    continuation: Continuation | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _text(self.operation_id, "Pi A2 operation"))
        if not isinstance(self.episode_id, EpisodeId) or not isinstance(self.turn_id, TurnId):
            raise TypeError("Pi A2 start requires exact EpisodeId and TurnId values")
        if (
            not isinstance(self.prompt, str)
            or not self.prompt
            or "\0" in self.prompt
            or len(self.prompt.encode()) > _MAX_PROMPT_BYTES
        ):
            raise ValueError("Pi A2 prompt must be bounded non-empty text")
        if type(self.workspace_archive) is not bytes:
            raise TypeError("Pi A2 workspace archive must be exact immutable bytes")
        digest = _digest(self.workspace_digest, "Pi A2 workspace digest")
        if sha256(self.workspace_archive).hexdigest() != digest:
            raise ValueError("Pi A2 workspace archive does not match its digest")
        validate_workspace_archive(
            self.workspace_archive,
            allow_links=False,
            forbidden_roots=frozenset({".git", STAGE_DIRECTORY}),
        )
        object.__setattr__(
            self,
            "workspace_correlation",
            _text(self.workspace_correlation, "Pi A2 workspace correlation", 512),
        )
        if type(self.policy) is not PiA2RuntimePolicy:
            raise TypeError("Pi A2 start requires exact PiA2RuntimePolicy")
        if self.continuation is not None and (
            not isinstance(self.continuation, Continuation)
            or self.continuation.descriptor != PI_CONTINUATION_DESCRIPTOR
            or self.continuation.state is not ContinuationState.IN_USE
        ):
            raise ValueError("Pi A2 continuation must be the claimed native Pi Continuation")


def _pi_a2_durable_fingerprint(
    config: PiA2RuntimeHostConfig,
    start: PiA2RuntimeStart,
    inner: str,
) -> str:
    """Bind prospective Pi work to exact workspace content and effective policy."""
    policy = start.policy
    identity = {
        "schema_version": _FINGERPRINT_SCHEMA_VERSION,
        "pi": _digest(inner, "Pi A2 inner fingerprint"),
        "workspace": {
            "digest": start.workspace_digest,
            "correlation": start.workspace_correlation,
        },
        "policy": {
            "capabilities": sorted(method.value for method in policy.capabilities),
            "writable_paths": sorted(policy.writable_paths),
            "writable_roots": sorted(policy.writable_roots),
            "denied_writable_roots": [".git", STAGE_DIRECTORY],
            "allowed_argv": (
                [list(argv) for argv in sorted(config.allowed_argv)]
                if ToolMethod.WORKSPACE_SHELL in policy.capabilities
                else []
            ),
            "test_command": (list(config.test_command) if ToolMethod.WORKSPACE_TEST in policy.capabilities else None),
            "max_tool_calls": policy.max_tool_calls,
        },
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class PiA2DirectAuthority:
    """Host-owned direct API-key authority supplied at most once per composer."""

    connection: ConnectionIdentity
    key_operations: KeyOperations
    supply_api_key: Callable[[], bytearray] = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.connection, ConnectionIdentity) or self.connection.profile != "api-key":
            raise ValueError("Pi A2 authority requires a direct API-key ConnectionIdentity")
        if any(not callable(getattr(self.key_operations, method, None)) for method in ("seal", "open", "erase")):
            raise TypeError("Pi A2 authority requires host KeyOperations")
        if not callable(self.supply_api_key):
            raise TypeError("Pi A2 authority supplier must be callable")


@dataclass(frozen=True)
class PiA2ScriptedCall:
    """One finite Hands request in a scripted conformance turn."""

    method: ToolMethod
    params_json: str
    expected_ok: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.method, ToolMethod) or type(self.expected_ok) is not bool:
            raise TypeError("scripted Pi call requires an exact method and expected verdict")
        try:
            params = json.loads(self.params_json)
        except json.JSONDecodeError:
            raise ValueError("scripted Pi call params must be JSON") from None
        if type(params) is not dict or len(self.params_json.encode()) > 8192:
            raise ValueError("scripted Pi call params must be a bounded JSON object")


@dataclass(frozen=True)
class PiA2ScriptedTurn:
    """Finite data interpreted by Petrus's credential-free scripted client."""

    output_text: str
    calls: tuple[PiA2ScriptedCall, ...] = ()
    delay_seconds: float = 0.0
    cleanup_verified: bool = True
    failure_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.output_text, str) or len(self.output_text.encode()) > 1_000_000:
            raise ValueError("scripted Pi output must be bounded text")
        calls = tuple(self.calls)
        if len(calls) > 256 or any(not isinstance(call, PiA2ScriptedCall) for call in calls):
            raise TypeError("scripted Pi calls must be finite PiA2ScriptedCall values")
        object.__setattr__(self, "calls", calls)
        if (
            isinstance(self.delay_seconds, bool)
            or not isinstance(self.delay_seconds, int | float)
            or not math.isfinite(self.delay_seconds)
            or self.delay_seconds < 0
            or self.delay_seconds > 60
        ):
            raise ValueError("scripted Pi delay must be finite and at most 60 seconds")
        if type(self.cleanup_verified) is not bool:
            raise TypeError("scripted Pi cleanup verdict must be boolean")
        if self.failure_code is not None:
            _text(self.failure_code, "scripted Pi failure code")


@dataclass(frozen=True)
class PiA2ScriptedReadiness:
    """Readiness for the Petrus-owned script interpreter, not a Pi installation."""

    support_label: str = _SCRIPTED_SUPPORT_LABEL
    ready: bool = True


class PiA2RuntimeHost(Protocol):
    """Public observation and operation surface for a composed Pi A2 host."""

    config: PiA2RuntimeHostConfig
    descriptor: CapabilityDescriptor
    snapshot: ResolutionSnapshot
    recovered_settlements: tuple[RuntimeTurnSettlement, ...]

    @property
    def authority_requested(self) -> bool: ...

    def probe(self) -> RuntimeProbeResult: ...
    def scripted_readiness(self) -> PiA2ScriptedReadiness: ...
    def start(self, start: PiA2RuntimeStart) -> RuntimeOperation: ...
    def load_output(self, reference: str) -> str: ...
    def load_workspace_archive(self, operation_id: str) -> bytes: ...
    def acknowledge(self, operation_id: str) -> PiOperationRecord: ...
    def close(self) -> bool: ...


class _ScriptedClient:
    def __init__(self, turn: PiA2ScriptedTurn, prior: PiContinuationPayloadV1 | None) -> None:
        self._turn, self._prior = turn, prior

    def run(self, gateway, invocation, current, deadline):
        stop = min(deadline, time.monotonic() + self._turn.delay_seconds)
        while time.monotonic() < stop:
            if not current():
                raise RuntimeProtocolError("cancelled")
            time.sleep(min(0.01, stop - time.monotonic()))
        if self._turn.failure_code is not None:
            raise RuntimeProtocolError(self._turn.failure_code)
        coordinates = invocation.attachment.coordinates()
        for index, call in enumerate(self._turn.calls):
            result = gateway.submit(
                {
                    "version": 1,
                    "call_id": f"scripted-{index}",
                    "episode_id": coordinates.episode_id,
                    "attachment_id": coordinates.attachment_id,
                    "attachment_epoch": coordinates.attachment_epoch,
                    "grant_epoch": invocation.grant_epoch,
                    "method": call.method.value,
                    "params": json.loads(call.params_json),
                }
            )
            if result.ok is not call.expected_ok:
                raise RuntimeProtocolError("script-expectation-failed")
        session = self._prior.session_id if self._prior is not None else _SCRIPTED_SESSION
        body = (
            self._prior.session_jsonl
            if self._prior is not None
            else json.dumps({"type": "session", "version": 3, "id": session}, separators=(",", ":")).encode() + b"\n"
        )
        body += json.dumps({"type": "message", "body": self._turn.output_text}, separators=(",", ":")).encode() + b"\n"
        return pi._HelperResult(pi._Candidate(session, self._turn.output_text, body), None, "turn-completed")

    def close(self) -> bool:
        return self._turn.cleanup_verified


class _ScriptedFactory:
    def __init__(self, script: tuple[PiA2ScriptedTurn, ...]) -> None:
        self._script = list(script)
        self._lock = threading.Lock()

    def create(self, **kwargs):
        with self._lock:
            if not self._script:
                raise RuntimeProtocolError("script-exhausted")
            turn = self._script.pop(0)
        return _ScriptedClient(turn, kwargs["prior"])


class _BodyStore(PiTurnOperations, PiContinuationOperations):
    """Private staged bodies committed atomically with aggregate cleanup proof."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._prepare_path()
        self._database = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False, timeout=5)
        os.chmod(self.path, 0o600)
        self._database.execute("PRAGMA journal_mode = DELETE")
        self._database.execute("PRAGMA synchronous = FULL")
        self._database.execute(
            """CREATE TABLE IF NOT EXISTS pi_a2_bodies (
                operation_id TEXT PRIMARY KEY,
                output_reference TEXT, output_text TEXT,
                continuation_reference TEXT, session_id TEXT,
                working_binding TEXT, session_jsonl BLOB,
                workspace_archive BLOB NOT NULL, workspace_digest TEXT NOT NULL,
                aggregate_verified INTEGER NOT NULL CHECK (aggregate_verified IN (0, 1)))"""
        )
        self._staged_outputs: dict[str, tuple[str, str]] = {}
        self._staged_continuations: dict[str, tuple[str, PiContinuationPayloadV1]] = {}
        self._lock = threading.RLock()
        self._closed = False

    def store_turn(self, operation_id: str, final_text: str) -> str:
        operation_id = _text(operation_id, "Pi A2 body operation")
        if not isinstance(final_text, str):
            raise TypeError("Pi A2 final output must be text")
        reference = f"pi-a2-output-{sha256((operation_id + '\0' + final_text).encode()).hexdigest()}"
        with self._lock:
            self._ensure_open()
            previous = self._staged_outputs.get(operation_id)
            candidate = (reference, final_text)
            if previous is not None and previous != candidate:
                raise RuntimeProtocolError("operation-conflict")
            self._staged_outputs[operation_id] = candidate
        return reference

    def store(self, operation_id: str, payload: PiContinuationPayloadV1) -> str:
        operation_id = _text(operation_id, "Pi A2 body operation")
        if not isinstance(payload, PiContinuationPayloadV1):
            raise TypeError("Pi A2 continuation body must be PiContinuationPayloadV1")
        digest = sha256(
            operation_id.encode()
            + b"\0"
            + payload.session_id.encode()
            + b"\0"
            + payload.working_directory_binding.encode()
            + b"\0"
            + payload.session_jsonl
        ).hexdigest()
        reference = f"pi-a2-continuation-{digest}"
        with self._lock:
            self._ensure_open()
            previous = self._staged_continuations.get(operation_id)
            candidate = (reference, payload)
            if previous is not None and previous != candidate:
                raise RuntimeProtocolError("operation-conflict")
            self._staged_continuations[operation_id] = candidate
        return reference

    def commit(self, operation_id: str, settlement: RuntimeTurnSettlement, archive: bytes) -> None:
        operation_id = _text(operation_id, "Pi A2 body operation")
        if not isinstance(settlement, RuntimeTurnSettlement) or not isinstance(archive, bytes):
            raise TypeError("Pi A2 body commit requires settlement and workspace archive")
        digest = sha256(archive).hexdigest()
        with self._lock:
            self._ensure_open()
            output = self._staged_outputs.get(operation_id)
            continuation = self._staged_continuations.get(operation_id)
            if settlement.outcome is TurnOutcome.COMPLETED:
                if output is None or continuation is None:
                    raise RuntimeProtocolError("body-publication-incomplete")
                if (settlement.output_reference, settlement.continuation_reference) != (
                    output[0],
                    continuation[0],
                ):
                    raise RuntimeProtocolError("body-publication-mismatch")
            elif any(
                value is not None
                for value in (output, continuation, settlement.output_reference, settlement.continuation_reference)
            ):
                raise RuntimeProtocolError("body-publication-mismatch")
            row = self._database.execute(
                "SELECT * FROM pi_a2_bodies WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            values = (
                operation_id,
                None if output is None else output[0],
                None if output is None else output[1],
                None if continuation is None else continuation[0],
                None if continuation is None else continuation[1].session_id,
                None if continuation is None else continuation[1].working_directory_binding,
                None if continuation is None else continuation[1].session_jsonl,
                archive,
                digest,
                0,
            )
            if row is not None:
                if tuple(row[:-1]) != values[:-1]:
                    raise RuntimeProtocolError("operation-conflict")
            else:
                self._database.execute("BEGIN IMMEDIATE")
                try:
                    self._database.execute(
                        "INSERT INTO pi_a2_bodies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        values,
                    )
                    self._database.commit()
                except BaseException:
                    self._database.rollback()
                    raise
            self.discard_staged(operation_id)

    def publish(self, operation_id: str) -> None:
        operation_id = _text(operation_id, "Pi A2 body operation")
        with self._lock:
            self._ensure_open()
            self._database.execute("BEGIN IMMEDIATE")
            try:
                updated = self._database.execute(
                    """UPDATE pi_a2_bodies SET aggregate_verified = 1
                       WHERE operation_id = ? AND aggregate_verified = 0""",
                    (operation_id,),
                )
                if updated.rowcount == 0 and not self.verified(operation_id):
                    raise RuntimeProtocolError("body-publication-incomplete")
                self._database.commit()
            except BaseException:
                self._database.rollback()
                raise

    def discard_staged(self, operation_id: str) -> None:
        with self._lock:
            self._staged_outputs.pop(operation_id, None)
            self._staged_continuations.pop(operation_id, None)

    def load(self, state_reference: str) -> PiContinuationPayloadV1:
        state_reference = _text(state_reference, "Pi A2 continuation reference", 512)
        with self._lock:
            self._ensure_open()
            row = self._database.execute(
                """SELECT session_id, working_binding, session_jsonl FROM pi_a2_bodies
                   WHERE continuation_reference = ? AND aggregate_verified = 1""",
                (state_reference,),
            ).fetchone()
        if row is None or any(value is None for value in row):
            raise RuntimeProtocolError("continuation-absent")
        return PiContinuationPayloadV1(str(row[0]), str(row[1]), bytes(row[2]))

    def load_output(self, reference: str) -> str:
        reference = _text(reference, "Pi A2 output reference", 512)
        with self._lock:
            self._ensure_open()
            row = self._database.execute(
                """SELECT output_text FROM pi_a2_bodies
                   WHERE output_reference = ? AND aggregate_verified = 1""",
                (reference,),
            ).fetchone()
        if row is None or row[0] is None:
            raise RuntimeProtocolError("output-absent")
        return str(row[0])

    def load_workspace_archive(self, operation_id: str) -> bytes:
        operation_id = _text(operation_id, "Pi A2 body operation")
        with self._lock:
            self._ensure_open()
            row = self._database.execute(
                """SELECT workspace_archive, workspace_digest FROM pi_a2_bodies
                   WHERE operation_id = ? AND aggregate_verified = 1""",
                (operation_id,),
            ).fetchone()
        if row is None:
            raise RuntimeProtocolError("workspace-archive-absent")
        archive = bytes(row[0])
        if sha256(archive).hexdigest() != str(row[1]):
            raise RuntimeProtocolError("workspace-archive-corrupt")
        return archive

    def continuation_workspace_digest(self, reference: str) -> str:
        reference = _text(reference, "Pi A2 continuation reference", 512)
        with self._lock:
            self._ensure_open()
            row = self._database.execute(
                """SELECT workspace_digest FROM pi_a2_bodies
                   WHERE continuation_reference = ? AND aggregate_verified = 1""",
                (reference,),
            ).fetchone()
        if row is None:
            raise RuntimeProtocolError("continuation-absent")
        try:
            return _digest(str(row[0]), "Pi A2 stored workspace digest")
        except ValueError:
            raise RuntimeProtocolError("workspace-archive-corrupt") from None

    def verified(self, operation_id: str) -> bool:
        with self._lock:
            self._ensure_open()
            return (
                self._database.execute(
                    "SELECT 1 FROM pi_a2_bodies WHERE operation_id = ? AND aggregate_verified = 1",
                    (operation_id,),
                ).fetchone()
                is not None
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._staged_outputs.clear()
            self._staged_continuations.clear()
            self._database.close()
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeProtocolError("host-closed")

    def _prepare_path(self) -> None:
        parent = self.path.parent
        if parent.is_symlink():
            raise StorageSecurityError("Pi A2 body-store parent must not be a symlink")
        metadata = parent.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_uid != os.geteuid()
        ):
            raise StorageSecurityError("Pi A2 body-store parent must be an owned mode-0700 directory")
        if self.path.is_symlink():
            raise StorageSecurityError("Pi A2 body-store file must not be a symlink")
        if not self.path.exists():
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(self.path, flags, 0o600)
            os.close(descriptor)
        metadata = self.path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.geteuid()
        ):
            raise StorageSecurityError("Pi A2 body-store file must be owned regular mode-0600")


class _ReplayOperation(RuntimeOperation):
    def __init__(self, record: PiOperationRecord) -> None:
        self._record = record
        self._cleanup: RuntimeOperationCleanup | None = None
        self._lock = threading.RLock()

    @property
    def operation_id(self) -> str:
        return self._record.operation_id

    def wait(self, timeout: float | None = None) -> RuntimeTurnSettlement:
        if timeout is not None:
            _positive(timeout, "Pi A2 wait timeout")
        with self._lock:
            if self._cleanup is not None:
                raise RuntimeProtocolError("operation-closed")
            return self._record.settlement()

    def cancel(self, reason: str) -> CancellationDisposition:
        _text(reason, "Pi A2 cancellation reason")
        return CancellationDisposition.TOO_LATE

    def close(self) -> RuntimeOperationCleanup:
        with self._lock:
            if self._cleanup is None:
                self._cleanup = self._record.cleanup_evidence()
            return self._cleanup


class _HostOperation(RuntimeOperation):
    def __init__(
        self,
        host: _PiA2RuntimeHost,
        inner: RuntimeOperation,
        attachment: EpisodeAttachment,
        territory_operation_id: str,
    ) -> None:
        self._host = host
        self._inner = inner
        self._attachment = attachment
        self._territory_operation_id = territory_operation_id
        self._settlement: RuntimeTurnSettlement | None = None
        self._cleanup: RuntimeOperationCleanup | None = None
        self._error: RuntimeProtocolError | None = None
        self._finalizing = False
        self._condition = threading.Condition(threading.RLock())

    @property
    def operation_id(self) -> str:
        return self._inner.operation_id

    def wait(self, timeout: float | None = None) -> RuntimeTurnSettlement:
        with self._condition:
            if self._cleanup is not None:
                raise RuntimeProtocolError("operation-closed")
            if self._settlement is not None:
                return self._settlement
            if self._error is not None:
                raise self._error
        result = self._inner.wait(timeout)
        return self._finalize(result)

    def cancel(self, reason: str) -> CancellationDisposition:
        return self._inner.cancel(reason)

    def close(self) -> RuntimeOperationCleanup:
        if not self._claim_finalization():
            with self._condition:
                assert self._cleanup is not None
                return self._cleanup
        try:
            receipt = self._host._adapter.receipt(self.operation_id)
            if receipt is None:
                self._inner.cancel("host-close")
                try:
                    receipt = self._inner.wait(self._host.config.cancellation_grace * 2)
                except TimeoutError, RuntimeProtocolError:
                    receipt = self._host._adapter.receipt(self.operation_id)
            if receipt is not None:
                try:
                    self._finalize_owned(receipt)
                except RuntimeProtocolError:
                    pass
            else:
                self._finalize_indeterminate_owned()
            with self._condition:
                assert self._cleanup is not None
                return self._cleanup
        finally:
            self._release_finalization()

    def _claim_finalization(self) -> bool:
        with self._condition:
            self._condition.wait_for(lambda: not self._finalizing)
            if self._cleanup is not None:
                return False
            self._finalizing = True
            return True

    def _release_finalization(self) -> None:
        with self._condition:
            self._finalizing = False
            self._condition.notify_all()

    def _finalize(self, result: RuntimeTurnSettlement) -> RuntimeTurnSettlement:
        if not self._claim_finalization():
            raise RuntimeProtocolError("operation-closed")
        try:
            return self._finalize_owned(result)
        finally:
            self._release_finalization()

    def _finalize_owned(self, result: RuntimeTurnSettlement) -> RuntimeTurnSettlement:
        try:
            inner_cleanup = self._inner.close()
            attachment_settlement = self._attachment.settle(drain_timeout=self._host.config.cancellation_grace * 2)
            verified = (
                inner_cleanup.verified
                and attachment_settlement.settlement.verified
                and self._host._provider.lookup(self._territory_operation_id) is None
            )
            if not verified:
                raise RuntimeProtocolError("host-cleanup-uncertain")
            self._host._bodies.commit(self.operation_id, result, attachment_settlement.archive)
            self._host._ledger.settle(self.operation_id, result)
            cleanup = RuntimeOperationCleanup(
                self.operation_id,
                inner_cleanup.disposition,
                inner_cleanup.code,
                inner_cleanup.physical_erasure_guaranteed,
            )
            self._host._ledger.upgrade_cleanup(self.operation_id, cleanup)
            self._host._bodies.publish(self.operation_id)
            with self._condition:
                self._settlement, self._cleanup = result, cleanup
            return result
        except BaseException as failure:
            error = (
                failure if isinstance(failure, RuntimeProtocolError) else RuntimeProtocolError("host-cleanup-uncertain")
            )
            self._host._bodies.discard_staged(self.operation_id)
            indeterminate = RuntimeTurnSettlement(
                self._attachment.episode_id,
                self._host._operation_turn(self.operation_id),
                TurnOutcome.INDETERMINATE,
                0,
                "host-cleanup-uncertain",
            )
            try:
                self._host._ledger.settle(self.operation_id, indeterminate)
            except Exception:
                pass
            with self._condition:
                self._error = error
                self._cleanup = RuntimeOperationCleanup(
                    self.operation_id, RuntimeCleanupDisposition.UNVERIFIED, "cleanup-uncertain"
                )
            raise error from None
        finally:
            self._host._operation_finished(self.operation_id)

    def _finalize_indeterminate_owned(self) -> None:
        try:
            inner_cleanup = self._inner.close()
        except Exception:
            inner_cleanup = RuntimeOperationCleanup(
                self.operation_id, RuntimeCleanupDisposition.UNVERIFIED, "cleanup-uncertain"
            )
        try:
            attachment_settlement = self._attachment.settle(drain_timeout=self._host.config.cancellation_grace * 2)
            aggregate_clean = (
                inner_cleanup.verified
                and attachment_settlement.settlement.verified
                and self._host._provider.lookup(self._territory_operation_id) is None
            )
        except Exception:
            aggregate_clean = False
        record = self._host._ledger.lookup(self.operation_id)
        assert record is not None
        indeterminate = RuntimeTurnSettlement(
            record.episode_id,
            record.turn_id,
            TurnOutcome.INDETERMINATE,
            0,
            "close-indeterminate",
        )
        try:
            self._host._ledger.settle(self.operation_id, indeterminate)
        except Exception:
            aggregate_clean = False
        cleanup = RuntimeOperationCleanup(
            self.operation_id,
            RuntimeCleanupDisposition.CLEAN if aggregate_clean else RuntimeCleanupDisposition.UNVERIFIED,
            "client-closed" if aggregate_clean else "cleanup-uncertain",
        )
        if aggregate_clean:
            try:
                self._host._ledger.upgrade_cleanup(self.operation_id, cleanup)
            except Exception:
                cleanup = RuntimeOperationCleanup(
                    self.operation_id, RuntimeCleanupDisposition.UNVERIFIED, "cleanup-uncertain"
                )
        with self._condition:
            self._cleanup = cleanup
        self._host._bodies.discard_staged(self.operation_id)
        self._host._operation_finished(self.operation_id)


class _PiA2RuntimeHost:
    """Owned Pi A2 Local host lifecycle with replay-before-authority."""

    descriptor = PI_NATIVE_A2_LOCAL
    snapshot = _SNAPSHOT

    def __init__(
        self,
        config: PiA2RuntimeHostConfig,
        authority: PiA2DirectAuthority,
        root: Path,
        storage: SqliteConnectionStorage,
        custody: AgentConnectionCustody,
        bodies: _BodyStore,
        ledger: SqlitePiOperationLedger,
        adapter: PiRuntimeAdapter,
        provider: EnvironmentProvider,
        clock: Callable[[], float],
    ) -> None:
        self.config, self.authority = config, authority
        self._root, self._storage, self._custody = root, storage, custody
        self._bodies, self._ledger, self._adapter = bodies, ledger, adapter
        self._provider, self._clock = provider, clock
        self._probe: RuntimeProbeResult | None = None
        self._scripted_conformance = False
        self._scripted_ready = False
        self._authority_requested = False
        self._closed = False
        self._close_error: RuntimeProtocolError | None = None
        self._lifecycle = uuid.uuid4().hex
        self._active: dict[str, _HostOperation] = {}
        self._turns: dict[str, TurnId] = {}
        self._territories: dict[str, str] = {}
        self._lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self.recovered_settlements = tuple(record.settlement() for record in self._ledger.recover())
        self._custody.recover(operation_id=self._lifecycle_operation("recover"))
        self._custody.enroll_host(config.host_id, operation_id=self._lifecycle_operation("enroll"))

    @property
    def authority_requested(self) -> bool:
        with self._lock:
            return self._authority_requested

    def probe(self) -> RuntimeProbeResult:
        with self._lock:
            self._ensure_open()
            if self._scripted_conformance:
                raise RuntimeProtocolError("scripted-readiness-only")
            result = self._adapter.probe(
                cli_path=self.config.cli_path,
                node_path=self.config.node_path,
                package_root=self.config.package_root,
            )
            self._probe = result
            return result

    def scripted_readiness(self) -> PiA2ScriptedReadiness:
        """Ready only Petrus's script interpreter without probing Pi or authority."""

        with self._lock:
            self._ensure_open()
            if not self._scripted_conformance:
                raise RuntimeProtocolError("scripted-readiness-unavailable")
            self._adapter._enable_scripted_conformance()
            self._scripted_ready = True
            return PiA2ScriptedReadiness()

    def start(self, start: PiA2RuntimeStart) -> RuntimeOperation:
        with self._lifecycle_lock:
            return self._start(start)

    def _start(self, start: PiA2RuntimeStart) -> RuntimeOperation:  # noqa: C901 - ordered admission boundary
        if not isinstance(start, PiA2RuntimeStart):
            raise TypeError("Pi A2 host requires PiA2RuntimeStart")
        fingerprint = self._fingerprint(start)
        with self._lock:
            self._ensure_open()
            existing = self._ledger.lookup(start.operation_id)
            if existing is not None:
                if existing.fingerprint != fingerprint:
                    raise RuntimeProtocolError("operation-conflict")
                live = self._active.get(start.operation_id)
                if live is not None:
                    return live
                if existing.phase is PiOperationPhase.SETTLED:
                    if existing.cleanup in (
                        RuntimeCleanupDisposition.CLEAN,
                        RuntimeCleanupDisposition.NOT_CREATED,
                    ) and self._bodies.verified(start.operation_id):
                        return _ReplayOperation(existing)
                    raise RuntimeProtocolError("operation-indeterminate")
                raise RuntimeProtocolError("operation-indeterminate")
            if (
                not start.policy.capabilities.issubset(self.config.capabilities)
                or start.policy.max_tool_calls > self.config.max_tool_calls
            ):
                raise RuntimeProtocolError("operation-policy-exceeds-host")
            if (
                start.continuation is not None
                and self._bodies.continuation_workspace_digest(start.continuation.state_reference)
                != start.workspace_digest
            ):
                raise RuntimeProtocolError("operation-conflict")
            self._require_ready()
            record = self._ledger.admit(start.operation_id, fingerprint, start.episode_id, start.turn_id)
            if record.fingerprint != fingerprint:
                raise RuntimeProtocolError("operation-conflict")
            self._turns[start.operation_id] = start.turn_id
        attachment: EpisodeAttachment | None = None
        territory_operation_id = self._territory_operation(start.operation_id)
        base_archive = start.workspace_archive
        try:
            connection = self._connection()
            binding = MotusAttachmentBinding.open(
                self._provider,
                territory_operation_id,
                EnvironmentSpec(required_capabilities=_REQUIRED_ENVIRONMENT_CAPABILITIES),
                workspace_archive_bytes=base_archive,
                input_digest=start.workspace_digest,
            )
            attachment = EpisodeAttachment(
                episode_id=start.episode_id,
                snapshot=self.snapshot,
                binding=binding,
                attachment_id=self._attachment_identity(start.operation_id),
                deadline=self._clock() + self.config.attachment_timeout,
                clock=self._clock,
            )
            workspace = MotusWorkspaceAdapter(
                self._provider,
                binding.execution,
                test_command=self.config.test_command,
                command_timeout=self.config.command_timeout,
            )
            gateway = attachment.gateway(workspace)
            grant = attachment.grants().open(
                start.policy.capabilities,
                writable_paths=start.policy.writable_paths,
                writable_roots=start.policy.writable_roots,
                denied_writable_roots=frozenset({".git", STAGE_DIRECTORY}),
                allowed_argv=self.config.allowed_argv,
                deadline=attachment.deadline,
                max_calls=start.policy.max_tool_calls,
            )
            invocation = PiRuntimeInvocation(
                start.operation_id,
                start.episode_id,
                start.turn_id,
                start.prompt,
                connection,
                attachment,
                gateway,
                grant.grant_epoch,
                start.continuation,
            )
            inner = self._adapter.start(invocation)
            operation = _HostOperation(self, inner, attachment, territory_operation_id)
            with self._lock:
                self._active[start.operation_id] = operation
                self._territories[start.operation_id] = territory_operation_id
            return operation
        except BaseException as failure:
            clean, archive = self._rollback_attachment(attachment, territory_operation_id, base_archive)
            settlement = RuntimeTurnSettlement(
                start.episode_id,
                start.turn_id,
                TurnOutcome.FAILED if clean else TurnOutcome.INDETERMINATE,
                0,
                "runtime-start-failed" if clean else "host-cleanup-uncertain",
            )
            if clean:
                try:
                    self._bodies.commit(start.operation_id, settlement, archive)
                    self._ledger.settle(start.operation_id, settlement)
                    self._ledger.upgrade_cleanup(
                        start.operation_id,
                        RuntimeOperationCleanup(
                            start.operation_id,
                            RuntimeCleanupDisposition.NOT_CREATED,
                            "client-not-created",
                        ),
                    )
                    self._bodies.publish(start.operation_id)
                except Exception:
                    clean = False
            if not clean:
                try:
                    self._ledger.settle(start.operation_id, settlement)
                except Exception:
                    pass
            if isinstance(failure, RuntimeProtocolError):
                raise
            raise RuntimeProtocolError("runtime-start-failed" if clean else "host-cleanup-uncertain") from None

    def _fingerprint(self, start: PiA2RuntimeStart) -> str:
        return _pi_a2_durable_fingerprint(
            self.config,
            start,
            pi_durable_work_fingerprint(
                self._adapter.config,
                start.episode_id,
                start.turn_id,
                start.prompt,
                self.authority.connection,
                start.continuation,
            ),
        )

    def load_output(self, reference: str) -> str:
        with self._lock:
            self._ensure_open()
        return self._bodies.load_output(reference)

    def load_workspace_archive(self, operation_id: str) -> bytes:
        with self._lock:
            self._ensure_open()
        return self._bodies.load_workspace_archive(operation_id)

    def acknowledge(self, operation_id: str) -> PiOperationRecord:
        with self._lock:
            self._ensure_open()
        return self._ledger.acknowledge(operation_id)

    def close(self) -> bool:
        with self._lifecycle_lock:
            return self._close()

    def _close(self) -> bool:  # noqa: C901 - teardown remains ordered and best-effort
        with self._lock:
            if self._closed:
                if self._close_error is not None:
                    raise self._close_error
                return True
            self._closed = True
            operations = tuple(self._active.values())
        clean = True
        for operation in operations:
            try:
                clean = operation.close().verified and clean
            except Exception:
                clean = False
        try:
            clean = not any(not record.cleanup_evidence().verified for record in self._ledger.records()) and clean
        except Exception:
            clean = False
        for territory in tuple(self._territories.values()):
            try:
                clean = self._provider.lookup(territory) is None and clean
            except Exception:
                clean = False
        try:
            removal = self._custody.remove_host(self.config.host_id, operation_id=self._lifecycle_operation("remove"))
            clean = removal.cleanup.unresolved == 0 and clean
        except Exception:
            clean = False
        try:
            requires_erasure = self._stored_connection_requires_erasure()
        except Exception:
            requires_erasure = False
            clean = False
        if requires_erasure:
            try:
                revoked = self._custody.revoke(
                    self.authority.connection.connection_id,
                    operation_id=self._lifecycle_operation("revoke"),
                )
                clean = revoked.cleanup.unresolved == 0 and clean
                erased = self._custody.erase(
                    self.authority.connection.connection_id,
                    operation_id=self._lifecycle_operation("erase"),
                )
                clean = erased.cleanup.unresolved == 0 and erased.key_erasure.erased and clean
                clean = erased.connection.status is ConnectionStatus.REAUTHORIZATION_REQUIRED and clean
            except Exception:
                clean = False
        try:
            clean = not any(self._root.joinpath("materializations").iterdir()) and clean
        except FileNotFoundError:
            pass
        except Exception:
            clean = False
        try:
            clean = not any(self._root.joinpath("runtime").iterdir()) and clean
        except FileNotFoundError:
            pass
        except Exception:
            clean = False
        for collaborator in (self._bodies, self._ledger, self._storage):
            try:
                collaborator.close()
            except Exception:
                clean = False
        with self._lock:
            if not clean:
                self._close_error = RuntimeProtocolError("host-cleanup-uncertain")
        if self._close_error is not None:
            raise self._close_error
        return True

    def _connection(self):
        with self._lock:
            try:
                connection = self._custody.connection(self.authority.connection.connection_id)
            except CustodyError:
                connection = None
            if connection is not None and connection.status is ConnectionStatus.READY:
                if connection.identity != self.authority.connection:
                    raise RuntimeProtocolError("connection-identity-mismatch")
                return connection
            if self._authority_requested:
                raise RuntimeProtocolError("authority-unavailable")
            self._authority_requested = True
            supplied = self.authority.supply_api_key()
            if not isinstance(supplied, bytearray) or not supplied or len(supplied) > _MAX_KEY_BYTES:
                if isinstance(supplied, bytearray):
                    _erase(supplied)
                raise RuntimeProtocolError("credential-invalid")
            opaque = OpaqueState(supplied)
            _erase(supplied)
            try:
                return self._custody.authorize(
                    self.authority.connection,
                    opaque,
                    operation_id=self._lifecycle_operation("authorize"),
                )
            finally:
                opaque.erase()

    def _require_ready(self) -> None:
        if self._scripted_conformance:
            if not self._scripted_ready:
                raise RuntimeProtocolError("runtime-not-ready")
            return
        result = self._probe
        if result is None or result.disposition is not ProbeDisposition.READY or result.installation is None:
            raise RuntimeProtocolError("runtime-not-ready")
        installation = result.installation
        if (
            result.runtime != PI_NATIVE_A2_LOCAL.identity
            or installation.runtime != PI_NATIVE_A2_LOCAL.identity
            or installation.adapter_contract_version != 1
            or not _REQUIRED_INSTALLATION_CAPABILITIES.issubset(installation.capabilities)
        ):
            raise RuntimeProtocolError("runtime-incompatible")

    def _stored_connection_requires_erasure(self) -> bool:
        for connection in self._storage.load().connections:
            if connection.connection_id == self.authority.connection.connection_id:
                return connection.status != ConnectionStatus.REAUTHORIZATION_REQUIRED.value
        return False

    def _rollback_attachment(
        self,
        attachment: EpisodeAttachment | None,
        territory_operation_id: str,
        base_archive: bytes,
    ) -> tuple[bool, bytes]:
        if attachment is not None:
            try:
                settled = attachment.settle(drain_timeout=self.config.cancellation_grace * 2)
                return (
                    settled.settlement.verified and self._provider.lookup(territory_operation_id) is None,
                    settled.archive,
                )
            except Exception:
                return False, b""
        try:
            lease = self._provider.lookup(territory_operation_id)
            if lease is None:
                return True, base_archive
            cleanup = self._provider.destroy(lease)
            return cleanup.verified and self._provider.lookup(territory_operation_id) is None, base_archive
        except Exception:
            return False, b""

    def _operation_finished(self, operation_id: str) -> None:
        with self._lock:
            self._active.pop(operation_id, None)

    def _operation_turn(self, operation_id: str) -> TurnId:
        with self._lock:
            turn = self._turns.get(operation_id)
        if turn is None:
            record = self._ledger.lookup(operation_id)
            if record is None:
                raise RuntimeProtocolError("operation-absent")
            return record.turn_id
        return turn

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeProtocolError("host-closed")

    def _lifecycle_operation(self, purpose: str) -> str:
        return f"pi-a2-{self._lifecycle}-{purpose}"

    @staticmethod
    def _territory_operation(operation_id: str) -> str:
        return f"pi-a2-territory-{sha256(operation_id.encode()).hexdigest()}"

    @staticmethod
    def _attachment_identity(operation_id: str) -> str:
        return f"pi-a2-attachment-{sha256(operation_id.encode()).hexdigest()}"


def compose_pi_a2_runtime(
    *,
    config: PiA2RuntimeHostConfig,
    authority: PiA2DirectAuthority,
    clock: Callable[[], float] = time.monotonic,
) -> PiA2RuntimeHost:
    """Compose the external-qualification host with exact owned collaborators."""

    return _compose_pi_a2_runtime(
        config=config,
        authority=authority,
        provider=LocalProcessEnvironment(),
        clock=clock,
        client_factory=None,
    )


def _compose_pi_a2_runtime(  # noqa: C901 - composition rollback owns each acquired collaborator
    *,
    config: PiA2RuntimeHostConfig,
    authority: PiA2DirectAuthority,
    provider: EnvironmentProvider,
    clock: Callable[[], float],
    client_factory: object | None,
) -> _PiA2RuntimeHost:
    """Internal collaborator-aware construction for bounded failure injection."""

    if not isinstance(config, PiA2RuntimeHostConfig) or not isinstance(authority, PiA2DirectAuthority):
        raise TypeError("Pi A2 composition requires exact config and authority values")
    if authority.connection.provider != config.provider:
        raise ValueError("Pi A2 authority provider must match the configured provider")
    if not callable(clock):
        raise TypeError("Pi A2 clock must be callable")
    if any(
        not callable(getattr(provider, method, None))
        for method in ("lookup", "create", "attach", "execute", "export", "destroy")
    ):
        raise TypeError("Pi A2 provider must implement the public Motus environment contract")
    if getattr(provider, "provider", None) != "local-process":
        raise ValueError("Pi A2 host supports only the Local Motus provider")
    if not _REQUIRED_ENVIRONMENT_CAPABILITIES.issubset(
        frozenset(cast(Iterable[str], getattr(provider, "capabilities", ())))
    ):
        raise ValueError("Pi A2 Local provider lacks required capabilities")
    root = _private_root(config.state_root)
    runtime_root = _private_subdirectory(root, "runtime")
    storage: SqliteConnectionStorage | None = None
    bodies: _BodyStore | None = None
    ledger: SqlitePiOperationLedger | None = None
    try:
        storage = SqliteConnectionStorage(root / "connection.sqlite3")
        materializer = PrivateFileMaterializer(root / "materializations")
        custody = AgentConnectionCustody(storage, authority.key_operations, materializer, clock=clock)
        bodies = _BodyStore(root / "bodies.sqlite3")
        ledger = SqlitePiOperationLedger(root / "operations.sqlite3")
        adapter = PiRuntimeAdapter(
            PiRuntimeConfig(
                config.provider,
                config.model,
                config.working_directory,
                runtime_root,
                host_id=config.host_id,
                credential_ttl=config.credential_ttl,
                wall_timeout=config.wall_timeout,
                cancellation_grace=config.cancellation_grace,
                cc_patch=False,
                territory_profile="local",
            ),
            PiContinuationCodec(bodies),
            bodies,
            custody,
            clock=clock,
            client_factory=cast(Any, client_factory),
        )
        return _PiA2RuntimeHost(
            config,
            authority,
            root,
            storage,
            custody,
            bodies,
            ledger,
            adapter,
            provider,
            clock,
        )
    except BaseException:
        for collaborator in (ledger, bodies, storage):
            if collaborator is not None:
                try:
                    collaborator.close()
                except Exception:
                    pass
        raise


def compose_pi_a2_scripted_runtime(
    *,
    config: PiA2RuntimeHostConfig,
    authority: PiA2DirectAuthority,
    script: tuple[PiA2ScriptedTurn, ...],
    clock: Callable[[], float] = time.monotonic,
) -> PiA2RuntimeHost:
    """Compose the supported credential-free scripted host lifecycle.

    This public seam qualifies Petrus-owned Pi A2 Local composition and
    lifecycle only. It neither probes nor claims an external Pi, model, or
    provider installation. Callers supply only finite immutable script data;
    Petrus owns the interpreter and exact ``LocalProcessEnvironment``.
    """

    if not isinstance(script, tuple) or not script or any(type(turn) is not PiA2ScriptedTurn for turn in script):
        raise TypeError("scripted Pi conformance requires finite PiA2ScriptedTurn data")
    return _compose_pi_a2_scripted_client_runtime(
        config=config,
        authority=authority,
        client_factory=_ScriptedFactory(script),
        clock=clock,
    )


def _compose_pi_a2_scripted_client_runtime(
    *,
    config: PiA2RuntimeHostConfig,
    authority: PiA2DirectAuthority,
    client_factory: object,
    provider: EnvironmentProvider | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> _PiA2RuntimeHost:
    """Internal conformance harness for exercising host failure boundaries."""

    host = _compose_pi_a2_runtime(
        config=config,
        authority=authority,
        provider=provider or LocalProcessEnvironment(),
        clock=clock,
        client_factory=client_factory,
    )
    host._scripted_conformance = True
    return host


__all__ = [
    "PiA2DirectAuthority",
    "PiA2RuntimeHost",
    "PiA2RuntimeHostConfig",
    "PiA2RuntimePolicy",
    "PiA2ScriptedCall",
    "PiA2ScriptedReadiness",
    "PiA2ScriptedTurn",
    "PiA2RuntimeStart",
    "compose_pi_a2_runtime",
    "compose_pi_a2_scripted_runtime",
]
