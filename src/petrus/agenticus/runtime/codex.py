"""Exact stock Codex A2 Local and A3 Gondolin production runtime lanes.

Codex owns the loop and rollout format.  Agenticus fences connection custody
and publishes only opaque rollout/output references; Motus owns the local
process and the two provider-private file roots.
"""

from __future__ import annotations

import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import UUID

from petrus.agenticus.attachment.binding import MotusAttachmentBinding
from petrus.agenticus.attachment.episode import EpisodeAttachment, EpisodeAttachmentError
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorIdentity, DescriptorKind
from petrus.agenticus.connection.custody import (
    AdmissionResult,
    AgentConnectionCustody,
    AttachmentFence,
    CleanupEvidence,
    ConnectionStatus,
    ConnectionView,
    LeaseMode,
    Materialization,
    PublicationResult,
    ReleaseResult,
)
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
from petrus.agenticus.runtime.profiles import CODEX_A2_LOCAL, CODEX_A3_GONDOLIN
from petrus.agenticus.runtime.result import RuntimeTurnSettlement
from petrus.agenticus.thread.continuation import Continuation, ContinuationDescriptor, ContinuationState
from petrus.agenticus.thread.identity import EpisodeId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome
from petrus.motus.execution import (
    MAX_COMMAND_OUTPUT_BYTES,
    MAX_PRIVATE_FILE_BYTES,
    Command,
    EnvironmentCapability,
    LeaseIdentity,
    LeaseState,
    PrivateFile,
    PrivateFileRef,
    PrivateFileTransfer,
)

CODEX_VERSION = "0.145.0"
CODEX_SOURCE_COMMIT = "1e85ca099e4265bf89f4016772d299816e231bb3"
CODEX_NPM_INTEGRITY = "sha512-/PSPSFujjjmiyVFvG2yu/grOFhsWdokTH8t2KGWhXSo/M5n/dIDsnbsnO82/7bLtIoDuzQf7ATBUMWqPWQINlQ=="
CODEX_SOURCE = f"npm:@openai/codex@{CODEX_VERSION}#commit={CODEX_SOURCE_COMMIT}#integrity={CODEX_NPM_INTEGRITY}"

CODEX_GONDOLIN_VERSION = "0.146.0"
CODEX_GONDOLIN_SDK_VERSION = "0.12.0"
CODEX_GONDOLIN_IMAGE_REF = "petrus-cv10-agents:amp1785543452-codex01460-gondolin0120"
CODEX_GONDOLIN_BUILD_ID = "49aac5ff-ea3f-5f46-a67a-cdc613ac4827"
CODEX_GONDOLIN_OCI_DIGEST = "sha256:9c7e769eb44f37b1e802c55dc43ee222e7b6c907fad3de8c01404a3b6c61124f"
CODEX_GONDOLIN_SOURCE = (
    f"gondolin:{CODEX_GONDOLIN_IMAGE_REF}#build={CODEX_GONDOLIN_BUILD_ID}#oci={CODEX_GONDOLIN_OCI_DIGEST}"
)

_PROGRAM_ID = DescriptorIdentity(DescriptorKind.PROGRAM, "codex.provider-managed", 1)
_CONTINUATION_ID = DescriptorIdentity(DescriptorKind.CONTINUATION, "codex.native-rollout", 1)
_CONNECTION_ID = DescriptorIdentity(DescriptorKind.CONNECTION, "codex.file-auth", 1)
_HANDS_ID = DescriptorIdentity(DescriptorKind.HANDS, "codex.collocated", 1)
_TERRITORY_ID = DescriptorIdentity(DescriptorKind.TERRITORY, "motus.local", 1)
_GONDOLIN_TERRITORY_ID = DescriptorIdentity(DescriptorKind.TERRITORY, "motus.gondolin", 1)

CODEX_CONTINUATION_DESCRIPTOR = ContinuationDescriptor(_CONTINUATION_ID, _PROGRAM_ID)
CODEX_PROGRAM = AgentProgramDescriptor(
    identity=_PROGRAM_ID,
    ownership=ProgramOwnership.PROVIDER,
    accepted_continuations=(ContinuationRequirement(_CONTINUATION_ID, _PROGRAM_ID),),
    produced_continuation=_CONTINUATION_ID,
    owns_steering=False,
    owns_evaluation=False,
)
CODEX_PROGRAM_CAPABILITIES = CapabilityDescriptor(_PROGRAM_ID, frozenset({"program.provider-owned"}))
CODEX_CONTINUATION_CAPABILITIES = CapabilityDescriptor(_CONTINUATION_ID, frozenset({"continuation.codex-native"}))
CODEX_CONNECTION_CAPABILITIES = CapabilityDescriptor(_CONNECTION_ID, frozenset({"connection.codex"}))
CODEX_COLLOCATED_HANDS = CapabilityDescriptor(_HANDS_ID, frozenset({"hands.collocated"}))
CODEX_LOCAL_TERRITORY = CapabilityDescriptor(_TERRITORY_ID, frozenset())
CODEX_GONDOLIN_TERRITORY = CapabilityDescriptor(_GONDOLIN_TERRITORY_ID, frozenset())

_MAX_PROMPT_BYTES = 64 * 1024
_ROLLOUT = re.compile(
    r"sessions/(?P<year>[0-9]{4})/(?P<month>0[1-9]|1[0-2])/(?P<day>0[1-9]|[12][0-9]|3[01])/"
    r"rollout-[A-Za-z0-9_.-]+-(?P<thread>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl"
)
_ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


def _text(value: object, name: str, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > maximum
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError(f"{name} must be bounded non-empty text")
    return value


def _uuid(value: object) -> str:
    value = _text(value, "Codex thread identity", 36)
    try:
        parsed = UUID(value)
    except ValueError, AttributeError:
        raise ValueError("Codex thread identity must be a canonical UUID") from None
    if str(parsed) != value:
        raise ValueError("Codex thread identity must be a canonical UUID")
    return value


def _rollout_path(value: object, thread_id: str) -> str:
    value = _text(value, "Codex rollout metadata", 256)
    match = _ROLLOUT.fullmatch(value)
    if match is None or match.group("thread") != thread_id:
        raise ValueError("Codex rollout metadata must be a safe provider-relative path for its thread")
    return value


def _final_text(value: object) -> str:
    if not isinstance(value, str):
        raise RuntimeProtocolError("malformed-agent-message")
    sanitized = _ANSI_ESCAPE.sub("", value)
    sanitized = "".join(
        character if character in "\n\r\t" or (32 <= ord(character) and not 127 <= ord(character) <= 159) else "�"
        for character in sanitized
    )
    if len(sanitized.encode()) > MAX_COMMAND_OUTPUT_BYTES:
        raise RuntimeProtocolError("agent-message-overflow")
    return sanitized


@dataclass(frozen=True)
class CodexContinuationPayloadV1:
    thread_id: str
    rollout_path: str
    rollout: bytes = field(repr=False)
    schema_version: int = field(default=1, init=False)

    def __post_init__(self) -> None:
        thread = _uuid(self.thread_id)
        object.__setattr__(self, "thread_id", thread)
        object.__setattr__(self, "rollout_path", _rollout_path(self.rollout_path, thread))
        if not isinstance(self.rollout, bytes):
            raise TypeError("Codex rollout must be opaque bytes")
        if not self.rollout or len(self.rollout) > MAX_PRIVATE_FILE_BYTES:
            raise ValueError("Codex rollout must be one non-empty bounded file")


@runtime_checkable
class CodexContinuationOperations(Protocol):
    def store(self, operation_id: str, payload: CodexContinuationPayloadV1) -> str: ...
    def load(self, state_reference: str) -> CodexContinuationPayloadV1: ...


@runtime_checkable
class CodexTurnOperations(Protocol):
    def store_turn(self, operation_id: str, thread_id: str, final_text: str) -> str: ...


class CodexContinuationCodec:
    descriptor = CODEX_CONTINUATION_DESCRIPTOR

    def __init__(self, operations: CodexContinuationOperations) -> None:
        if not isinstance(operations, CodexContinuationOperations):
            raise TypeError("Codex codec requires CodexContinuationOperations")
        self._operations = operations

    def store(self, operation_id: str, payload: CodexContinuationPayloadV1) -> str:
        return _text(self._operations.store(_text(operation_id, "Codex operation"), payload), "state reference", 512)

    def load(self, continuation: Continuation) -> CodexContinuationPayloadV1:
        if not isinstance(continuation, Continuation) or continuation.descriptor != self.descriptor:
            raise ValueError("Codex Continuation does not match this runtime")
        value = self._operations.load(continuation.state_reference)
        if not isinstance(value, CodexContinuationPayloadV1):
            raise TypeError("Codex custody returned a foreign payload")
        return value


@runtime_checkable
class CodexConnectionCustody(Protocol):
    def materialize(
        self, connection_id: str, host_id: str, *, mode: LeaseMode, ttl: float, operation_id: str
    ) -> Materialization: ...
    def activate(self, materialization: Materialization, *, operation_id: str) -> None: ...
    def admit_result(self, fence: AttachmentFence, *, operation_id: str) -> AdmissionResult: ...
    def checkpoint(self, materialization: Materialization, *, operation_id: str) -> PublicationResult: ...
    def release(self, materialization: Materialization, *, operation_id: str) -> ReleaseResult: ...


@dataclass(frozen=True)
class CodexRuntimeConfig:
    host_id: str
    credential_ttl: float = 300.0
    command_timeout: float = 300.0
    output_limit: int = MAX_COMMAND_OUTPUT_BYTES
    cancellation_grace: float = 10.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "host_id", _text(self.host_id, "Codex enrolled host"))
        for value, name in (
            (self.credential_ttl, "credential TTL"),
            (self.command_timeout, "command timeout"),
            (self.cancellation_grace, "cancellation grace"),
        ):
            if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Codex {name} must be positive and finite")
        if type(self.output_limit) is not int or not 0 < self.output_limit <= MAX_COMMAND_OUTPUT_BYTES:
            raise ValueError("Codex output limit is outside the Motus command bound")


@dataclass(frozen=True)
class CodexRuntimeInvocation:
    operation_id: str
    episode_id: EpisodeId
    turn_id: TurnId
    prompt: str = field(repr=False)
    connection: ConnectionView
    attachment: EpisodeAttachment = field(repr=False)
    continuation: Continuation | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _text(self.operation_id, "Codex operation"))
        if not isinstance(self.episode_id, EpisodeId) or not isinstance(self.turn_id, TurnId):
            raise TypeError("Codex invocation requires exact EpisodeId and TurnId")
        if (
            not isinstance(self.prompt, str)
            or not self.prompt
            or len(self.prompt.encode()) > _MAX_PROMPT_BYTES
            or "\x00" in self.prompt
        ):
            raise ValueError("Codex prompt must be bounded non-empty text")
        if not isinstance(self.connection, ConnectionView) or self.connection.status is not ConnectionStatus.READY:
            raise ValueError("Codex connection must be ready")
        if self.connection.identity.provider != "codex" or self.connection.identity.profile != "file-auth":
            raise ValueError("Codex invocation requires the Codex file-auth profile")
        if not isinstance(self.attachment, EpisodeAttachment) or self.attachment.episode_id != self.episode_id:
            raise ValueError("Codex invocation requires its exact Episode Attachment")
        if self.continuation is not None and not isinstance(self.continuation, Continuation):
            raise TypeError("Codex continuation must be Continuation or None")


# Kept private deliberately: this is stock Codex's retained-home choreography,
# not a general Motus filesystem API. It is passed only as a Motus command.
_HELPER_SOURCE = r"""
import json, os, re, stat, sys
MAX=1000000
PAT=re.compile(r"sessions/(?P<y>[0-9]{4})/(?P<m>0[1-9]|1[0-2])/(?P<d>0[1-9]|[12][0-9]|3[01])/rollout-[A-Za-z0-9_.-]+-(?P<t>[0-9a-f-]{36})\.jsonl")
HOME=os.environ["CODEX_HOME"]
TRANSFER=os.environ["PETRUS_CODEX_ROLLOUT_ROOT"]
LEAF=os.path.join(TRANSFER,"rollout.jsonl")

def fail():
 raise RuntimeError()

def directory(path):
 value=os.lstat(path)
 if stat.S_ISLNK(value.st_mode) or not stat.S_ISDIR(value.st_mode) or stat.S_IMODE(value.st_mode)!=0o700 or value.st_uid!=os.geteuid(): fail()

def opened(path, flags, strict=True):
 fd=os.open(path,flags|os.O_NOFOLLOW)
 value=os.fstat(fd)
 if not stat.S_ISREG(value.st_mode) or value.st_uid!=os.geteuid() or value.st_nlink!=1 or (strict and stat.S_IMODE(value.st_mode)!=0o600):
  os.close(fd); fail()
 return fd,value

def read(path, nonempty=True, strict=True, normalize=False):
 fd,before=opened(path,os.O_RDONLY,strict)
 try:
  if normalize:
   os.fchmod(fd,0o600); before=os.fstat(fd)
  chunks=[]; retained=0
  while retained<=MAX:
   chunk=os.read(fd,min(65536,MAX+1-retained))
   if not chunk: break
   chunks.append(chunk); retained+=len(chunk)
  after=os.fstat(fd)
 finally: os.close(fd)
 data=b"".join(chunks)
 stable=(before.st_dev,before.st_ino,before.st_mode,before.st_uid,before.st_nlink,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_mode,after.st_uid,after.st_nlink,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
 if not stable or len(data)!=after.st_size or len(data)>MAX or (nonempty and not data): fail()
 return data

def write_all(fd,data):
 pending=memoryview(data)
 while pending:
  count=os.write(fd,pending)
  if count<=0: fail()
  pending=pending[count:]

def replace(path,data):
 fd,_=opened(path,os.O_WRONLY)
 try:
  os.ftruncate(fd,0); os.fchmod(fd,0o600); write_all(fd,data); os.fsync(fd)
 finally: os.close(fd)
 read(path)

def create(path,data):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  os.fchmod(fd,0o600); write_all(fd,data); os.fsync(fd)
 finally: os.close(fd)
 read(path)

def safe_dirs(parts):
 path=HOME
 for part in parts:
  path=os.path.join(path,part)
  try: os.mkdir(path,0o700)
  except FileExistsError: pass
  directory(path)
 return path

def provider_directory(path):
 value=os.lstat(path)
 if stat.S_ISLNK(value.st_mode) or not stat.S_ISDIR(value.st_mode) or value.st_uid!=os.geteuid(): fail()

def scrub():
 violation=False
 for root,dirs,files in os.walk(HOME,topdown=False,followlinks=False):
  for name in files:
   path=os.path.join(root,name)
   if path==os.path.join(HOME,"auth.json"): continue
   value=os.lstat(path)
   violation=violation or stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode) or value.st_uid!=os.geteuid() or (stat.S_ISREG(value.st_mode) and value.st_nlink!=1)
   os.unlink(path)
  for name in dirs:
   path=os.path.join(root,name); value=os.lstat(path)
   if stat.S_ISLNK(value.st_mode):
    violation=True; os.unlink(path)
   else:
    if not stat.S_ISDIR(value.st_mode) or value.st_uid!=os.geteuid(): violation=True
    os.rmdir(path)
 read(os.path.join(HOME,"auth.json"))
 if os.listdir(HOME)!=["auth.json"]: fail()
 return violation

def main():
 directory(HOME); directory(TRANSFER)
 read(os.path.join(HOME,"auth.json"))
 mode=sys.argv[1]
 if mode=="stage":
  thread,relative=sys.argv[2:4]; match=PAT.fullmatch(relative)
  if not match or match.group("t")!=thread: fail()
  data=read(LEAF); parent=safe_dirs(relative.split("/")[:-1]); target=os.path.join(parent,relative.split("/")[-1])
  if os.path.lexists(target): fail()
  create(target,data); print('{"ok":true}')
 elif mode=="collect":
  thread=sys.argv[2]; found=[]
  for root,dirs,files in os.walk(HOME,topdown=True,followlinks=False):
   for name in dirs:
    provider_directory(os.path.join(root,name))
   for name in files:
    path=os.path.join(root,name); relative=os.path.relpath(path,HOME).replace(os.sep,"/")
    match=PAT.fullmatch(relative)
    if match: found.append((path,relative,match.group("t")))
  if len(found)!=1 or found[0][2]!=thread: fail()
  source,relative,_=found[0]; data=read(source,strict=False,normalize=True); replace(LEAF,data)
  if scrub(): fail()
  print(json.dumps({"ok":True,"rollout_path":relative},separators=(",",":")))
 elif mode=="scrub":
  if scrub(): fail()
  print('{"ok":true}')
 else: fail()

try: main()
except Exception: raise SystemExit(64)
"""


def _parse_helper(stdout: bytes, *, collect: bool) -> str | None:
    if len(stdout) > 512:
        raise RuntimeProtocolError("helper-protocol")
    try:
        value = json.loads(stdout)
    except UnicodeDecodeError, json.JSONDecodeError:
        raise RuntimeProtocolError("helper-protocol") from None
    expected = {"ok", "rollout_path"} if collect else {"ok"}
    if not isinstance(value, dict) or set(value) != expected or value["ok"] is not True:
        raise RuntimeProtocolError("helper-protocol")
    return value.get("rollout_path")


def _connection_cleanup_verified(value: object, operation_id: str, attachment_id: str) -> bool:
    if not isinstance(value, PublicationResult | ReleaseResult) or value.operation_id != operation_id:
        return False
    cleanup = value.cleanup
    return (
        isinstance(cleanup, CleanupEvidence)
        and cleanup.attachment_id == attachment_id
        and (cleanup.removed or cleanup.already_absent)
        and not cleanup.security_violation
    )


@dataclass(frozen=True)
class _Candidate:
    thread_id: str
    completed: bool
    text: str | None = field(repr=False)


def _parse_jsonl(raw: bytes, returncode: int) -> _Candidate:  # noqa: C901 - exact protocol admission
    try:
        lines = raw.split(b"\n")
        if lines and lines[-1] == b"":
            lines.pop()
        if not lines or any(not line for line in lines):
            raise RuntimeProtocolError("malformed-jsonl")
        events = [json.loads(line.decode("utf-8")) for line in lines]
    except UnicodeDecodeError, json.JSONDecodeError:
        raise RuntimeProtocolError("malformed-jsonl") from None
    if not events or any(not isinstance(event, dict) or not isinstance(event.get("type"), str) for event in events):
        raise RuntimeProtocolError("malformed-jsonl")
    allowed = {
        "thread.started",
        "turn.started",
        "item.started",
        "item.updated",
        "item.completed",
        "turn.completed",
        "turn.failed",
        "error",
    }
    if any(event["type"] not in allowed for event in events):
        raise RuntimeProtocolError("unknown-event")
    started = [event for event in events if event["type"] == "thread.started"]
    turns = [event for event in events if event["type"] == "turn.started"]
    terminals = [event for event in events if event["type"] in {"turn.completed", "turn.failed"}]
    if (
        len(started) != 1
        or len(turns) != 1
        or len(terminals) != 1
        or events[0] is not started[0]
        or events.index(turns[0]) != 1
        or events[-1] is not terminals[0]
    ):
        raise RuntimeProtocolError("codex-lifecycle")
    try:
        thread = _uuid(started[0].get("thread_id"))
    except ValueError:
        raise RuntimeProtocolError("malformed-thread-id") from None
    completed = terminals[0]["type"] == "turn.completed"
    if (completed and returncode != 0) or (not completed and returncode != 1):
        raise RuntimeProtocolError("exit-inconsistent")
    if completed:
        if not isinstance(terminals[0].get("usage"), dict):
            raise RuntimeProtocolError("malformed-terminal")
    else:
        failure = terminals[0].get("error")
        if not isinstance(failure, dict) or not isinstance(failure.get("message"), str):
            raise RuntimeProtocolError("malformed-terminal")
    item_types = {
        "agent_message",
        "reasoning",
        "command_execution",
        "file_change",
        "mcp_tool_call",
        "collab_tool_call",
        "web_search",
        "todo_list",
        "error",
    }
    latest = None
    completed_items: set[str] = set()
    for event in events[2:-1]:
        event_type = event["type"]
        if event_type == "error":
            if not isinstance(event.get("message"), str):
                raise RuntimeProtocolError("malformed-error")
            continue
        if event_type not in {"item.started", "item.updated", "item.completed"}:
            raise RuntimeProtocolError("codex-lifecycle")
        item = event.get("item")
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not item["id"]
            or item.get("type") not in item_types
        ):
            raise RuntimeProtocolError("malformed-item")
        if event_type == "item.completed":
            if item["id"] in completed_items:
                raise RuntimeProtocolError("duplicate-item-terminal")
            completed_items.add(item["id"])
            if item["type"] == "agent_message":
                latest = _final_text(item.get("text"))
    if completed and latest is None:
        raise RuntimeProtocolError("missing-agent-message")
    return _Candidate(thread, completed, latest)


@dataclass(frozen=True)
class _Key:
    episode: str
    turn: str
    prompt: str
    connection: str
    authority_epoch: int
    state_version: int
    attachment: str
    attachment_epoch: int
    continuation_id: str | None
    continuation_lineage: str | None
    continuation_reference_digest: str | None
    continuation_thread: str | None
    continuation_path: str | None
    continuation_digest: str | None


class _CodexOperation:
    def __init__(
        self,
        adapter: CodexRuntimeAdapter,
        invocation: CodexRuntimeInvocation,
        key: _Key,
        prior: CodexContinuationPayloadV1 | None,
        executable: str,
        execution_path: str,
    ) -> None:
        self.adapter, self.invocation, self.key, self.prior = adapter, invocation, key, prior
        self.executable, self.execution_path = executable, execution_path
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None
        self._result: RuntimeTurnSettlement | None = None
        self._cleanup: RuntimeOperationCleanup | None = None
        self._cancelled = False
        self._publishing = False
        self._cleanup_disposition = RuntimeCleanupDisposition.UNVERIFIED

    @property
    def operation_id(self) -> str:
        return self.invocation.operation_id

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name=f"codex-{sha256(self.operation_id.encode()).hexdigest()[:12]}", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        result, cleanup = self.adapter._execute(
            self.invocation,
            self.prior,
            self._is_current,
            self._claim_publication,
            self.executable,
            self.execution_path,
        )
        with self._condition:
            if self._cancelled and result.outcome is not TurnOutcome.CANCELLED:
                result = self.adapter._settle(self.invocation, TurnOutcome.CANCELLED, 0, "cancelled")
            self._result, self._cleanup_disposition = result, cleanup
            self._condition.notify_all()

    def _is_current(self) -> bool:
        with self._condition:
            return not self._cancelled

    def _claim_publication(self) -> str | None:
        with self._condition:
            if self._cancelled:
                return "cancelled"
            if self.adapter._clock() >= self.invocation.attachment.deadline:
                return "deadline-exceeded"
            self._publishing = True
            return None

    def wait(self, timeout: float | None = None) -> RuntimeTurnSettlement:
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("Codex operation wait timeout must be positive and finite")
        with self._condition:
            if self._cleanup is not None:
                raise RuntimeProtocolError("operation-closed")
            self._condition.wait_for(lambda: self._result is not None, timeout)
            if self._result is None:
                raise TimeoutError("Codex runtime operation has not settled")
            return self._result

    def cancel(self, reason: str) -> CancellationDisposition:
        _text(reason, "Codex cancellation reason")
        with self._condition:
            if self._result is not None or self._publishing:
                return CancellationDisposition.TOO_LATE
            if self._cancelled:
                return CancellationDisposition.ALREADY_REQUESTED
            self._cancelled = True
        try:
            self.invocation.attachment.cancel(reason)
        except EpisodeAttachmentError:
            # The current predicate still makes a not-yet-launched command
            # superseded; an attachment/result settlement may have won the
            # same boundary race.
            pass
        return CancellationDisposition.REQUESTED

    def close(self) -> RuntimeOperationCleanup:
        with self._condition:
            if self._cleanup is not None:
                return self._cleanup
            if self._result is None and not self._cancelled:
                raise RuntimeProtocolError("operation-active")
            thread = self._thread
        if thread is not None:
            thread.join(self.adapter._config.cancellation_grace)
        disposition = self._cleanup_disposition
        if thread is not None and thread.is_alive():
            disposition = RuntimeCleanupDisposition.UNVERIFIED
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


class CodexRuntimeAdapter:
    """The one exact @openai/codex 0.145.0 Local Motus adapter."""

    descriptor = CODEX_A2_LOCAL
    program = CODEX_PROGRAM
    continuation_descriptor = CODEX_CONTINUATION_DESCRIPTOR
    territory = CODEX_LOCAL_TERRITORY
    _runtime_provider = "local-process"
    _helper_executable = sys.executable

    def __init__(
        self,
        config: CodexRuntimeConfig,
        codec: CodexContinuationCodec,
        turns: CodexTurnOperations,
        custody: AgentConnectionCustody | CodexConnectionCustody,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            not isinstance(config, CodexRuntimeConfig)
            or not isinstance(codec, CodexContinuationCodec)
            or not isinstance(turns, CodexTurnOperations)
            or not isinstance(custody, CodexConnectionCustody)
        ):
            raise TypeError("Codex adapter requires exact config, codec, turn custody, and connection custody")
        self._config, self._codec, self._turns, self._custody, self._clock = config, codec, turns, custody, clock
        self._installation: RuntimeInstallation | None = None
        self._executable: str | None = None
        self._execution_path: str | None = None
        self._operations: dict[str, _CodexOperation] = {}
        self._lock = threading.RLock()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(host_id={self._config.host_id!r}, ready={self._installation is not None!r})"

    def probe(self) -> RuntimeProbeResult:
        executable = shutil.which("codex")
        node = shutil.which("node")
        if executable is None or node is None:
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.NOT_INSTALLED,
                    issues=(ProbeIssue("client-not-installed", "codex" if executable is None else "node"),),
                ),
                None,
            )
        executable = os.path.abspath(executable)
        node = os.path.abspath(node)
        try:
            version_output = subprocess.run(
                (executable, "--version"), capture_output=True, text=True, check=True, timeout=10
            ).stdout.strip()
            help_text = subprocess.run(
                (executable, "exec", "--help"), capture_output=True, text=True, check=True, timeout=10
            ).stdout
            resume_help = subprocess.run(
                (executable, "exec", "resume", "--help"), capture_output=True, text=True, check=True, timeout=10
            ).stdout
        except OSError, subprocess.SubprocessError:
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.UNAVAILABLE,
                    issues=(ProbeIssue("client-unavailable", "codex"),),
                ),
                None,
            )
        version_match = re.fullmatch(r"codex-cli ([^\s]+)", version_output)
        version = version_match.group(1) if version_match is not None else "unparseable"
        installation = RuntimeInstallation(
            self.descriptor.identity,
            1,
            (InstalledComponent("openai-codex", version, CODEX_SOURCE),),
            platform.system().lower() or "unknown",
            platform.machine().lower() or "unknown",
            frozenset({"runtime.cancel", "runtime.continue", "runtime.local", "runtime.provider-managed"}),
        )
        if version != CODEX_VERSION:
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.INCOMPATIBLE,
                    installation,
                    (ProbeIssue("version-mismatch", "codex"),),
                ),
                None,
            )
        required = (
            "--json",
            "--color",
            "--sandbox",
            "--config",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
        )
        if not all(option in help_text for option in required) or "SESSION_ID" not in resume_help:
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.UNAVAILABLE,
                    installation,
                    (ProbeIssue("protocol-unavailable", "codex"),),
                ),
                None,
            )
        execution_path = os.pathsep.join(
            dict.fromkeys((str(Path(executable).parent), str(Path(node).parent), *os.defpath.split(os.pathsep)))
        )
        return self._record(
            RuntimeProbeResult(self.descriptor.identity, ProbeDisposition.READY, installation),
            executable,
            execution_path,
        )

    def _record(
        self,
        result: RuntimeProbeResult,
        executable: str | None,
        execution_path: str | None = None,
    ) -> RuntimeProbeResult:
        with self._lock:
            self._installation = result.installation if result.disposition is ProbeDisposition.READY else None
            self._executable = executable if self._installation is not None else None
            self._execution_path = execution_path if self._installation is not None else None
        return result

    def start(self, invocation: CodexRuntimeInvocation) -> RuntimeOperation:
        if not isinstance(invocation, CodexRuntimeInvocation):
            raise TypeError("Codex runtime requires CodexRuntimeInvocation")
        if self._installation is None or self._executable is None or self._execution_path is None:
            raise RuntimeProtocolError("runtime-not-ready")
        self._validate(invocation)
        if invocation.continuation is not None and invocation.continuation.state is not ContinuationState.IN_USE:
            raise RuntimeProtocolError("continuation-not-claimed")
        prior = self._codec.load(invocation.continuation) if invocation.continuation else None
        c = invocation.attachment.coordinates()
        key = _Key(
            invocation.episode_id.value,
            invocation.turn_id.value,
            sha256(invocation.prompt.encode()).hexdigest(),
            invocation.connection.identity.connection_id,
            invocation.connection.authority_epoch,
            invocation.connection.state_version,
            c.attachment_id,
            c.attachment_epoch,
            invocation.continuation.id.value if invocation.continuation else None,
            invocation.continuation.thread.value if invocation.continuation else None,
            sha256(invocation.continuation.state_reference.encode()).hexdigest() if invocation.continuation else None,
            prior.thread_id if prior else None,
            prior.rollout_path if prior else None,
            sha256(prior.rollout).hexdigest() if prior else None,
        )
        with self._lock:
            executable, execution_path = self._executable, self._execution_path
            if self._installation is None or executable is None or execution_path is None:
                raise RuntimeProtocolError("runtime-not-ready")
            old = self._operations.get(invocation.operation_id)
            if old:
                if old.key != key:
                    raise RuntimeProtocolError("operation-conflict")
                return old
            operation = _CodexOperation(self, invocation, key, prior, executable, execution_path)
            self._operations[invocation.operation_id] = operation
        try:
            operation.start()
        except Exception:
            with self._lock:
                self._operations.pop(invocation.operation_id, None)
            raise
        return operation

    def _validate(self, invocation: CodexRuntimeInvocation) -> None:
        self._validate_attachment(invocation.attachment)

    def _validate_attachment(self, attachment: EpisodeAttachment) -> None:
        if not isinstance(attachment, EpisodeAttachment):
            raise RuntimeProtocolError("attachment-binding-mismatch")
        expected = {
            DescriptorKind.RUNTIME: self.descriptor.identity,
            DescriptorKind.CONNECTION: _CONNECTION_ID,
            DescriptorKind.PROGRAM: _PROGRAM_ID,
            DescriptorKind.HANDS: _HANDS_ID,
            DescriptorKind.TERRITORY: self.territory.identity,
            DescriptorKind.CONTINUATION: _CONTINUATION_ID,
        }
        if any(
            (d := attachment.snapshot.descriptor(kind)) is None or d.identity != identity
            for kind, identity in expected.items()
        ):
            raise RuntimeProtocolError("resolution-mismatch")
        effect = attachment.snapshot.descriptor(DescriptorKind.EFFECT)
        if effect is None or "effect.host-fenced" not in effect.offers:
            raise RuntimeProtocolError("resolution-mismatch")
        binding = attachment.binding
        if not isinstance(binding, MotusAttachmentBinding):
            raise RuntimeProtocolError("attachment-binding-mismatch")
        if not isinstance(binding.provider, PrivateFileTransfer):
            raise RuntimeProtocolError("private-transfer-required")
        lease = binding.execution.lease
        if (
            lease.state is not LeaseState.READY
            or lease.provider != self._runtime_provider
            or EnvironmentCapability.PRIVATE_FILE_TRANSFER.value not in lease.capabilities
        ):
            raise RuntimeProtocolError("runtime-private-lease-required")

    def _settle(
        self,
        inv: CodexRuntimeInvocation,
        outcome: TurnOutcome,
        appends: int,
        code: str,
        output: str | None = None,
        continuation: str | None = None,
    ) -> RuntimeTurnSettlement:
        return RuntimeTurnSettlement(inv.episode_id, inv.turn_id, outcome, appends, code, output, continuation)

    def _execute(  # noqa: C901 - custody publication and cleanup precedence is intentionally explicit
        self,
        inv: CodexRuntimeInvocation,
        prior: CodexContinuationPayloadV1 | None,
        current: Callable[[], bool],
        claim_publication: Callable[[], str | None],
        executable: str,
        execution_path: str,
    ) -> tuple[RuntimeTurnSettlement, RuntimeCleanupDisposition]:
        binding = inv.attachment.binding
        assert isinstance(binding, MotusAttachmentBinding)
        transfer = binding.provider
        assert isinstance(transfer, PrivateFileTransfer)
        materialization = auth_ref = rollout_ref = None
        materialization_attempted = False
        connection_settled = False
        connection_clean = False
        private_clean = True
        home_touched = False
        home_scrubbed = False
        cleanup_disposition = RuntimeCleanupDisposition.UNVERIFIED
        ids = {
            name: f"{inv.operation_id}.{name}" for name in ("materialize", "activate", "admit", "checkpoint", "release")
        }

        def remaining() -> float:
            value = inv.attachment.deadline - self._clock()
            if value <= 0:
                raise RuntimeProtocolError("deadline-exceeded")
            return min(value, self._config.command_timeout)

        def command_is_current() -> bool:
            return current() and self._clock() < inv.attachment.deadline

        def helper(mode: str, *values: str, check_current: bool = True) -> str | None:
            assert auth_ref is not None and rollout_ref is not None
            result = binding.execute(
                Command(
                    (self._helper_executable, "-c", _HELPER_SOURCE, mode, *values),
                    timeout=(
                        remaining()
                        if check_current
                        else min(self._config.command_timeout, self._config.cancellation_grace)
                    ),
                    output_limit=512,
                    private_roots={"CODEX_HOME": auth_ref, "PETRUS_CODEX_ROLLOUT_ROOT": rollout_ref},
                    is_current=command_is_current if check_current else None,
                )
            )
            if (
                result.returncode != 0
                or result.stderr
                or result.timed_out
                or result.superseded
                or result.output_truncated
            ):
                raise RuntimeProtocolError(f"{mode}-failed")
            return _parse_helper(result.stdout, collect=mode == "collect")

        try:
            if not current():
                raise RuntimeProtocolError("cancelled")
            ttl = remaining()
            materialization_attempted = True
            materialization = self._custody.materialize(
                inv.connection.identity.connection_id,
                self._config.host_id,
                mode=LeaseMode.REFRESH,
                ttl=min(self._config.credential_ttl, ttl),
                operation_id=ids["materialize"],
            )
            if not isinstance(materialization, Materialization) or materialization.mode is not LeaseMode.REFRESH:
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
            if not current():
                raise RuntimeProtocolError("cancelled")
            self._custody.activate(materialization, operation_id=ids["activate"])
            if not current():
                raise RuntimeProtocolError("cancelled")
            auth_ref = transfer.import_private_file(
                binding.execution, PrivateFile("auth.json", materialization.home.read())
            )
            private_clean = False
            rollout_ref = transfer.import_private_file(
                binding.execution, PrivateFile("rollout.jsonl", prior.rollout if prior else b"")
            )
            if prior:
                home_touched = True
                helper("stage", prior.thread_id, prior.rollout_path)
            common = (
                "--json",
                "--color",
                "never",
                "--sandbox",
                "read-only",
                "--config",
                "cli_auth_credentials_store=file",
                "--skip-git-repo-check",
                "--ignore-user-config",
                "--ignore-rules",
            )
            argv = (
                executable,
                "exec",
                *common,
                *(("resume", prior.thread_id) if prior else ()),
                "--",
                inv.prompt,
            )
            home_touched = True
            result = binding.execute(
                Command(
                    argv,
                    environment={
                        "LANG": "C.UTF-8",
                        "NO_COLOR": "1",
                        "PATH": execution_path,
                    },
                    timeout=remaining(),
                    output_limit=self._config.output_limit,
                    private_roots={"CODEX_HOME": auth_ref},
                    is_current=command_is_current,
                )
            )
            if result.timed_out:
                raise RuntimeProtocolError("command-timeout")
            if result.superseded:
                raise RuntimeProtocolError("command-superseded")
            if result.output_truncated:
                raise RuntimeProtocolError("output-overflow")
            if result.returncode < 0:
                raise RuntimeProtocolError("command-signal")
            candidate = _parse_jsonl(result.stdout, result.returncode)
            if prior and candidate.thread_id != prior.thread_id:
                raise RuntimeProtocolError("continuation-thread-mismatch")
            path = helper("collect", candidate.thread_id)
            home_scrubbed = True
            assert path is not None
            path = _rollout_path(path, candidate.thread_id)
            auth = transfer.export_private_file(binding.execution, auth_ref).content
            rollout = transfer.export_private_file(binding.execution, rollout_ref).content
            materialization.home.replace(auth)
            if not command_is_current():
                raise RuntimeProtocolError("command-superseded")
            continuation = self._codec.store(
                inv.operation_id, CodexContinuationPayloadV1(candidate.thread_id, path, rollout)
            )
            output = None
            if candidate.completed:
                output = _text(
                    self._turns.store_turn(inv.operation_id, candidate.thread_id, candidate.text or ""),
                    "Codex output reference",
                    512,
                )
            for ref in (auth_ref, rollout_ref):
                if not transfer.delete_private_file(binding.execution, ref).verified:
                    raise RuntimeProtocolError("private-cleanup-uncertain")
            if not transfer.cleanup_private_files(binding.execution).verified:
                raise RuntimeProtocolError("private-cleanup-uncertain")
            private_clean = True
            publication_error = claim_publication()
            if publication_error is not None:
                raise RuntimeProtocolError(publication_error)
            admission = self._custody.admit_result(materialization.fence, operation_id=ids["admit"])
            if (
                not isinstance(admission, AdmissionResult)
                or admission.operation_id != ids["admit"]
                or admission.purpose != "result"
                or admission.attachment_id != fence.attachment_id
            ):
                raise RuntimeProtocolError("custody-admission-mismatch")
            publication = self._custody.checkpoint(materialization, operation_id=ids["checkpoint"])
            connection_settled = True
            connection_clean = _connection_cleanup_verified(publication, ids["checkpoint"], fence.attachment_id)
            if not connection_clean:
                raise RuntimeProtocolError("connection-cleanup-uncertain")
            connection = publication.connection
            if (
                connection.identity != inv.connection.identity
                or connection.status is not ConnectionStatus.READY
                or connection.authority_epoch != fence.authority_epoch
                or connection.state_version != fence.base_version + 1
            ):
                raise RuntimeProtocolError("connection-publication-mismatch")
            cleanup_disposition = RuntimeCleanupDisposition.CLEAN
            if candidate.completed:
                return (
                    self._settle(inv, TurnOutcome.COMPLETED, 1, "turn-completed", output, continuation),
                    cleanup_disposition,
                )
            return (
                self._settle(inv, TurnOutcome.FAILED, 0, "provider-failed", continuation=continuation),
                cleanup_disposition,
            )
        except RuntimeProtocolError as error:
            code = error.code
        except Exception:
            code = "runtime-failed"
        finally:
            if not private_clean:
                scrubbed = home_scrubbed or not home_touched
                if not scrubbed and home_touched and auth_ref is not None and rollout_ref is not None:
                    try:
                        helper("scrub", check_current=False)
                        scrubbed = True
                    except Exception:
                        pass
                try:
                    cleanup = transfer.cleanup_private_files(binding.execution)
                    private_clean = scrubbed and cleanup.verified
                except Exception:
                    private_clean = False
            if materialization is not None and not connection_settled:
                try:
                    released = self._custody.release(materialization, operation_id=ids["release"])
                    connection_settled = True
                    connection_clean = _connection_cleanup_verified(
                        released, ids["release"], materialization.fence.attachment_id
                    )
                except Exception:
                    connection_clean = False
            if connection_clean and private_clean:
                cleanup_disposition = RuntimeCleanupDisposition.CLEAN
            elif not materialization_attempted and materialization is None and auth_ref is None and rollout_ref is None:
                cleanup_disposition = RuntimeCleanupDisposition.NOT_CREATED
            else:
                cleanup_disposition = RuntimeCleanupDisposition.UNVERIFIED
        outcome = TurnOutcome.CANCELLED if not current() else TurnOutcome.FAILED
        return (
            self._settle(inv, outcome, 0, "cancelled" if outcome is TurnOutcome.CANCELLED else code),
            cleanup_disposition,
        )


class CodexGondolinRuntimeAdapter(CodexRuntimeAdapter):
    """The exact stock Codex 0.146.0 lane inside a qualified Gondolin lease."""

    descriptor = CODEX_A3_GONDOLIN
    territory = CODEX_GONDOLIN_TERRITORY
    _runtime_provider = "gondolin"
    _helper_executable = "/usr/bin/python3"
    _guest_executable = "/usr/local/bin/codex"
    _guest_path = "/usr/local/bin:/usr/bin:/bin"

    def __init__(
        self,
        config: CodexRuntimeConfig,
        codec: CodexContinuationCodec,
        turns: CodexTurnOperations,
        custody: AgentConnectionCustody | CodexConnectionCustody,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(config, codec, turns, custody, clock=clock)
        self._qualified_attachments: set[tuple[LeaseIdentity, str]] = set()

    def _private_file_probe(self, binding: MotusAttachmentBinding, remaining: float) -> bool:
        transfer = binding.provider
        assert isinstance(transfer, PrivateFileTransfer)
        probe_file = PrivateFile("probe", b"agenticus-codex-a3-before")
        expected = PrivateFile("probe", b"agenticus-codex-a3-after")
        reference: PrivateFileRef | None = None
        passed = False
        cleaned = False
        try:
            reference = transfer.import_private_file(binding.execution, probe_file)
            result = binding.execute(
                Command(
                    (
                        self._helper_executable,
                        "-c",
                        "import os,pathlib,sys; p=pathlib.Path(os.environ['PETRUS_PROBE'])/'probe'; sys.exit(64) if p.read_bytes()!=b'agenticus-codex-a3-before' else p.write_bytes(b'agenticus-codex-a3-after')",
                    ),
                    environment={"LANG": "C.UTF-8", "PATH": self._guest_path},
                    timeout=remaining,
                    output_limit=64,
                    private_roots={"PETRUS_PROBE": reference},
                )
            )
            passed = (
                result.returncode == 0
                and not result.stdout
                and not result.stderr
                and not result.timed_out
                and not result.superseded
                and not result.output_truncated
                and transfer.export_private_file(binding.execution, reference) == expected
            )
        except OSError, RuntimeError, ValueError:
            passed = False
        finally:
            try:
                deleted = reference is None or transfer.delete_private_file(binding.execution, reference).verified
            except OSError, RuntimeError, ValueError:
                deleted = False
            try:
                attachment_cleaned = transfer.cleanup_private_files(binding.execution).verified
            except OSError, RuntimeError, ValueError:
                attachment_cleaned = False
            cleaned = deleted and attachment_cleaned
        return passed and cleaned

    def _credential_free_probe_command(
        self,
        binding: MotusAttachmentBinding,
        remaining: float,
        argv: tuple[str, ...],
    ) -> str | None:
        try:
            result = binding.execute(
                Command(
                    argv,
                    environment={"LANG": "C.UTF-8", "NO_COLOR": "1", "PATH": self._guest_path},
                    timeout=remaining,
                    output_limit=128 * 1024,
                )
            )
            if (
                result.returncode != 0
                or result.stderr
                or result.timed_out
                or result.superseded
                or result.output_truncated
            ):
                return None
            return result.stdout.decode("utf-8").strip()
        except OSError, RuntimeError, UnicodeDecodeError, ValueError:
            return None

    def probe(self, attachment: EpisodeAttachment | None = None) -> RuntimeProbeResult:
        """Probe the exact credential-free guest lease before materialization."""

        if attachment is None:
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.UNAVAILABLE,
                    issues=(ProbeIssue("territory-probe-required", "gondolin"),),
                ),
                None,
            )
        self._validate_attachment(attachment)
        binding = attachment.binding
        assert isinstance(binding, MotusAttachmentBinding)
        key = (binding.lease_identity, binding.execution.attachment_id)
        with self._lock:
            self._qualified_attachments.discard(key)
        remaining = min(self._config.command_timeout, attachment.deadline - self._clock())
        if remaining <= 0:
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.UNAVAILABLE,
                    issues=(ProbeIssue("territory-unavailable", "gondolin"),),
                ),
                None,
            )

        if not self._private_file_probe(binding, remaining):
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.UNAVAILABLE,
                    issues=(ProbeIssue("territory-probe-failed", "gondolin"),),
                ),
                None,
            )

        version_output = self._credential_free_probe_command(
            binding,
            remaining,
            (self._guest_executable, "--version"),
        )
        architecture = self._credential_free_probe_command(binding, remaining, ("/bin/uname", "-m"))
        if version_output is None or architecture is None:
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.UNAVAILABLE,
                    issues=(ProbeIssue("client-unavailable", "codex"),),
                ),
                None,
            )
        version_match = re.fullmatch(r"codex-cli ([^\s]+)", version_output)
        version = version_match.group(1) if version_match is not None else "unparseable"
        if re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", architecture) is None:
            architecture = "unparseable"
        installation = RuntimeInstallation(
            self.descriptor.identity,
            1,
            (InstalledComponent("openai-codex", version, CODEX_GONDOLIN_SOURCE),),
            "linux",
            architecture,
            frozenset(
                {
                    "runtime.cancel",
                    "runtime.continue",
                    "runtime.gondolin",
                    "runtime.provider-managed",
                }
            ),
        )
        if version != CODEX_GONDOLIN_VERSION or architecture != "aarch64":
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.INCOMPATIBLE,
                    installation,
                    (
                        ProbeIssue(
                            "version-mismatch" if version != CODEX_GONDOLIN_VERSION else "platform-mismatch", "codex"
                        ),
                    ),
                ),
                None,
            )
        help_text = self._credential_free_probe_command(
            binding,
            remaining,
            (self._guest_executable, "exec", "--help"),
        )
        resume_help = self._credential_free_probe_command(
            binding,
            remaining,
            (self._guest_executable, "exec", "resume", "--help"),
        )
        required = (
            "--json",
            "--color",
            "--sandbox",
            "--config",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
        )
        if (
            help_text is None
            or resume_help is None
            or not all(option in help_text for option in required)
            or "SESSION_ID" not in resume_help
        ):
            return self._record(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.UNAVAILABLE,
                    installation,
                    (ProbeIssue("protocol-unavailable", "codex"),),
                ),
                None,
            )
        result = self._record(
            RuntimeProbeResult(self.descriptor.identity, ProbeDisposition.READY, installation),
            self._guest_executable,
            self._guest_path,
        )
        with self._lock:
            self._qualified_attachments.add(key)
        return result

    def start(self, invocation: CodexRuntimeInvocation) -> RuntimeOperation:
        if not isinstance(invocation, CodexRuntimeInvocation):
            raise TypeError("Codex runtime requires CodexRuntimeInvocation")
        binding = invocation.attachment.binding
        if not isinstance(binding, MotusAttachmentBinding):
            raise RuntimeProtocolError("attachment-binding-mismatch")
        with self._lock:
            if (binding.lease_identity, binding.execution.attachment_id) not in self._qualified_attachments:
                raise RuntimeProtocolError("territory-not-qualified")
        return super().start(invocation)


__all__ = [
    "CODEX_COLLOCATED_HANDS",
    "CODEX_CONNECTION_CAPABILITIES",
    "CODEX_CONTINUATION_CAPABILITIES",
    "CODEX_CONTINUATION_DESCRIPTOR",
    "CODEX_GONDOLIN_BUILD_ID",
    "CODEX_GONDOLIN_IMAGE_REF",
    "CODEX_GONDOLIN_OCI_DIGEST",
    "CODEX_GONDOLIN_SDK_VERSION",
    "CODEX_GONDOLIN_TERRITORY",
    "CODEX_GONDOLIN_VERSION",
    "CODEX_LOCAL_TERRITORY",
    "CODEX_NPM_INTEGRITY",
    "CODEX_PROGRAM",
    "CODEX_PROGRAM_CAPABILITIES",
    "CODEX_SOURCE_COMMIT",
    "CODEX_VERSION",
    "CodexContinuationCodec",
    "CodexContinuationOperations",
    "CodexContinuationPayloadV1",
    "CodexGondolinRuntimeAdapter",
    "CodexRuntimeAdapter",
    "CodexRuntimeConfig",
    "CodexRuntimeInvocation",
    "CodexTurnOperations",
]
