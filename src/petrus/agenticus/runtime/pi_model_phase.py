"""Bounded public-Pi one-model-phase Activity adapter."""

from __future__ import annotations

import base64
import json
import math
import os
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
from petrus.agenticus.program.agent_net import (
    MAX_PROPOSALS,
    MODEL_PHASE_ACTIVITY,
    LoopState,
    ModelSettlement,
    Proposal,
    StopReason,
)
from petrus.agenticus.runtime.operation import RuntimeProtocolError
from petrus.agenticus.runtime.pi import PI_AI_VERSION, PI_API_KEY_CATALOG, PI_SDK_VERSION
from petrus.motus.activity import ActivityExecutionContext, ActivityInvocation

MAX_TRANSCRIPT_BYTES = 4_000_000
MAX_OUTPUT_BYTES = 1_000_000
MAX_MESSAGES = 10_000
MAX_FRAME_BYTES = 16 * 1024 * 1024
_MAX_TEXT = 256
_MAX_PROMPT = 64 * 1024
_MAX_REF = 512
_MAX_KEY = 8192
_LIMITS = {
    "frame": MAX_FRAME_BYTES,
    "output": MAX_OUTPUT_BYTES,
    "transcript": MAX_TRANSCRIPT_BYTES,
    "messages": MAX_MESSAGES,
}


def _strict(raw: bytes) -> object:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    return json.loads(
        raw.decode("utf-8", "strict"),
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        object_pairs_hook=unique,
    )


def _text(value: object, label: str, maximum: int = _MAX_TEXT) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > maximum
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError(f"Pi model phase {label} is invalid")
    return value


def _prompt(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > _MAX_PROMPT or "\0" in value:
        raise ValueError(f"Pi model phase {label} is invalid")
    return value


def _payload(value: bytes, maximum: int, label: str) -> bytes:
    if type(value) is not bytes or not value or len(value) > maximum:
        raise ValueError(f"Pi model phase {label} is invalid")
    decoded = _strict(value)
    if label == "transcript" and (
        type(decoded) is not list or len(decoded) > MAX_MESSAGES or any(type(x) is not dict for x in decoded)
    ):
        raise ValueError("Pi model phase transcript is invalid")
    if label == "assistant" and type(decoded) is not dict:
        raise ValueError("Pi model phase assistant is invalid")
    return value


@dataclass(frozen=True)
class PiModelPhaseContinuationPayloadV1:
    transcript_json: bytes = field(repr=False)
    schema_version: int = field(default=1, init=False)

    def __post_init__(self) -> None:
        _payload(self.transcript_json, MAX_TRANSCRIPT_BYTES, "transcript")


@dataclass(frozen=True)
class PiModelPhaseOutputPayloadV1:
    assistant_json: bytes = field(repr=False)
    schema_version: int = field(default=1, init=False)

    def __post_init__(self) -> None:
        _payload(self.assistant_json, MAX_OUTPUT_BYTES, "assistant")


@dataclass(frozen=True)
class PiModelPhasePublication:
    output_reference: str
    continuation_reference: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_reference", _text(self.output_reference, "output reference", _MAX_REF))
        object.__setattr__(
            self,
            "continuation_reference",
            _text(self.continuation_reference, "Continuation reference", _MAX_REF),
        )


@runtime_checkable
class PiModelPhaseOperations(Protocol):
    """Atomically load private Continuations and publish one complete phase."""

    def load_continuation(self, reference: str) -> PiModelPhaseContinuationPayloadV1: ...

    def publish(
        self,
        operation_id: str,
        output: PiModelPhaseOutputPayloadV1,
        continuation: PiModelPhaseContinuationPayloadV1,
    ) -> PiModelPhasePublication: ...


@runtime_checkable
class PiModelPhaseCustody(Protocol):
    def materialize(
        self, connection_id: str, host_id: str, *, mode: LeaseMode, ttl: float, operation_id: str
    ) -> Materialization: ...
    def admit_result(self, fence: AttachmentFence, *, operation_id: str) -> AdmissionResult: ...
    def release(self, materialization: Materialization, *, operation_id: str) -> ReleaseResult: ...


@dataclass(frozen=True)
class PiModelPhaseConfig:
    provider: str
    model: str
    host_id: str
    runtime_root: Path
    episode_id: str
    turn_id: str
    system_prompt: str = "You are an Agenticus workspace agent. Use only supplied tools."
    observation: str = "Continue."
    timeout: float = 120.0

    def __post_init__(self) -> None:
        for name in ("provider", "model", "host_id", "episode_id", "turn_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("system_prompt", "observation"):
            object.__setattr__(self, name, _prompt(getattr(self, name), name))
        if (self.provider, self.model) not in PI_API_KEY_CATALOG:
            raise ValueError("Pi model phase provider/model is outside the direct API-key catalog")
        if (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, int | float)
            or not math.isfinite(self.timeout)
            or self.timeout <= 0
        ):
            raise ValueError("Pi model phase timeout must be positive and finite")
        root = Path(self.runtime_root)
        if root.is_symlink():
            raise ValueError("Pi model phase runtime_root must be stable")
        root = root.resolve()
        if not root.is_dir() or root.stat().st_uid != os.geteuid() or stat.S_IMODE(root.stat().st_mode) != 0o700:
            raise ValueError("Pi model phase runtime_root must be owned mode-0700")
        object.__setattr__(self, "runtime_root", root)


@dataclass(frozen=True)
class _Candidate:
    assistant: bytes
    transcript: bytes


class _Client(Protocol):
    def run(self, frame: dict[str, object], timeout: float, heartbeat: Callable[[], None]) -> _Candidate: ...
    def close(self) -> bool: ...


class _Factory(Protocol):
    def create(self, **kwargs: object) -> _Client: ...


class _SubprocessClient:
    def __init__(self, *, node: str, helper: Path, entrypoint: str, private_root: Path) -> None:
        if not Path(node).is_absolute():
            raise RuntimeProtocolError("runtime-not-ready")
        env = {"HOME": str(private_root), "PATH": str(Path(node).parent), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        try:
            self.process = subprocess.Popen(
                (node, str(helper), entrypoint),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                start_new_session=True,
                bufsize=0,
            )
        except OSError:
            raise RuntimeProtocolError("helper-launch-failed") from None
        self.thread = threading.Thread(target=self._drain, daemon=True)
        self.thread.start()
        self.closed = False

    def _drain(self) -> None:
        if self.process.stderr:
            while self.process.stderr.read(65536):
                pass

    def run(  # noqa: C901 - framed process protocol
        self, frame: dict[str, object], timeout: float, heartbeat: Callable[[], None]
    ) -> _Candidate:
        raw = json.dumps(frame, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode() + b"\n"
        if len(raw) > MAX_FRAME_BYTES or not self.process.stdin or not self.process.stdout:
            raise RuntimeProtocolError("frame-overflow")
        selector = selectors.DefaultSelector()
        selector.register(self.process.stdin, selectors.EVENT_WRITE, "input")
        selector.register(self.process.stdout, selectors.EVENT_READ, "output")
        os.set_blocking(self.process.stdin.fileno(), False)
        buffer = bytearray()
        sent = 0
        input_open = output_open = True
        deadline = time.monotonic() + timeout
        heartbeat_at = time.monotonic() + min(5.0, timeout / 2)
        try:
            while input_open or output_open:
                if time.monotonic() >= deadline:
                    raise RuntimeProtocolError("deadline-exceeded")
                if time.monotonic() >= heartbeat_at:
                    try:
                        heartbeat()
                    except Exception:
                        raise RuntimeProtocolError("activity-stale") from None
                    heartbeat_at = time.monotonic() + min(5.0, timeout / 2)
                for key, _ in selector.select(0.02):
                    if key.data == "input":
                        try:
                            sent += os.write(key.fd, raw[sent:])
                        except BrokenPipeError:
                            sent = len(raw)
                        if sent == len(raw):
                            selector.unregister(self.process.stdin)
                            self.process.stdin.close()
                            input_open = False
                    else:
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(self.process.stdout)
                            output_open = False
                            continue
                        buffer.extend(chunk)
                        if len(buffer) > MAX_FRAME_BYTES:
                            raise RuntimeProtocolError("frame-overflow")
                if self.process.poll() is not None and input_open:
                    selector.unregister(self.process.stdin)
                    self.process.stdin.close()
                    input_open = False
            returncode = self.process.wait(timeout=0.1)
        finally:
            selector.close()
        if buffer.count(b"\n") != 1 or not buffer.endswith(b"\n"):
            raise RuntimeProtocolError("helper-protocol")
        try:
            answer = _strict(bytes(buffer[:-1]))
        except Exception:
            raise RuntimeProtocolError("malformed-frame") from None
        if type(answer) is not dict:
            raise RuntimeProtocolError("helper-protocol")
        answer_data = cast(dict[str, object], answer)
        if set(answer_data) == {"type", "code"} and answer_data["type"] == "failed":
            if returncode == 0 or answer_data["code"] not in {"provider-failed", "protocol-failed"}:
                raise RuntimeProtocolError("helper-protocol")
            raise RuntimeProtocolError(cast(str, answer_data["code"]))
        if (
            returncode != 0
            or set(answer_data) != {"type", "assistant", "transcript"}
            or answer_data["type"] != "complete"
        ):
            raise RuntimeProtocolError("helper-protocol")
        return _Candidate(
            _decode(answer_data["assistant"], MAX_OUTPUT_BYTES, "assistant"),
            _decode(answer_data["transcript"], MAX_TRANSCRIPT_BYTES, "transcript"),
        )

    def close(self) -> bool:
        if self.closed:
            return self.process.poll() is not None
        self.closed = True
        try:
            if self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=1)
        except OSError, subprocess.TimeoutExpired:
            return False
        self.thread.join(1)
        return not self.thread.is_alive()


class _SubprocessFactory:
    def create(self, **kwargs: object) -> _Client:
        return _SubprocessClient(
            node=cast(str, kwargs["node"]),
            helper=cast(Path, kwargs["helper"]),
            entrypoint=cast(str, kwargs["entrypoint"]),
            private_root=cast(Path, kwargs["private_root"]),
        )


class PiModelPhaseAdapter:
    def __init__(
        self,
        config: PiModelPhaseConfig,
        connection: ConnectionView,
        custody: PiModelPhaseCustody,
        operations: PiModelPhaseOperations,
        *,
        node: str = "node",
        sdk_entrypoint: str | None = None,
        client_factory: _Factory | None = None,
    ) -> None:
        if not isinstance(config, PiModelPhaseConfig) or not isinstance(connection, ConnectionView):
            raise TypeError("Pi model phase requires exact configuration and connection")
        if not isinstance(custody, PiModelPhaseCustody) or not isinstance(operations, PiModelPhaseOperations):
            raise TypeError("Pi model phase requires exact collaborators")
        if connection.status is not ConnectionStatus.READY or connection.identity.profile != "api-key":
            raise ValueError("Pi model phase requires a ready api-key connection")
        if connection.identity.provider != config.provider:
            raise ValueError("Pi model phase connection provider mismatch")
        self.config, self.connection, self.custody, self.operations = (
            config,
            connection,
            custody,
            operations,
        )
        self.node, self.sdk_entrypoint, self.factory = node, sdk_entrypoint, client_factory or _SubprocessFactory()
        self._probed = False

    def probe(self, package_root: str | Path) -> bool:
        self._probed = False
        try:
            node = shutil.which(self.node)
            if node is None:
                return False
            node_real = Path(node).resolve(strict=True)
            root = Path(package_root).resolve(strict=True)
            package = json.loads((root / "package.json").read_text())
            ai = json.loads((root / "node_modules/@earendil-works/pi-ai/package.json").read_text())
            version = subprocess.run(
                (str(node_real), "--version"), capture_output=True, text=True, check=True, timeout=10
            ).stdout.strip()
            match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", version)
            entry = (root / "dist/index.js").resolve(strict=True)
            helper = Path(__file__).with_name("pi_model_phase_helper.mjs").resolve(strict=True)
            if (
                package.get("name") != "@earendil-works/pi-coding-agent"
                or package.get("version") != PI_SDK_VERSION
                or ai.get("name") != "@earendil-works/pi-ai"
                or ai.get("version") != PI_AI_VERSION
                or match is None
                or tuple(map(int, match.groups())) < (22, 19, 0)
            ):
                return False
            run = subprocess.run(
                (str(node_real), str(helper), str(entry), "--probe"),
                capture_output=True,
                timeout=10,
                env={"HOME": os.devnull, "PATH": str(node_real.parent), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
            )
            if run.returncode or run.stderr or run.stdout != b'{"type":"probe","ok":true}\n':
                return False
            self.node = str(node_real)
            self.sdk_entrypoint = str(entry)
            self._probed = True
            return True
        except OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError:
            return False

    def __call__(  # noqa: C901 - Activity admission is one fail-closed boundary
        self, invocation: ActivityInvocation, *, context: ActivityExecutionContext
    ) -> object:
        if invocation.activity != MODEL_PHASE_ACTIVITY:
            raise RuntimeProtocolError("activity-mismatch")
        try:
            state = LoopState.from_data(invocation.input)
        except Exception:
            raise RuntimeProtocolError("input-invalid") from None
        if (state.episode_id, state.turn_id) != (self.config.episode_id, self.config.turn_id):
            raise RuntimeProtocolError("state-mismatch")
        operation = invocation.idempotency or context.attempt_id
        try:
            operation = _text(operation, "operation")
        except ValueError:
            raise RuntimeProtocolError("runtime-not-ready") from None
        if self.sdk_entrypoint is None or (
            isinstance(self.factory, _SubprocessFactory)
            and (not self._probed or not Path(self.node).is_absolute() or not Path(self.sdk_entrypoint).is_absolute())
        ):
            raise RuntimeProtocolError("runtime-not-ready")
        if state.phase > 1 and state.continuation_ref is None:
            raise RuntimeProtocolError("continuation-required")
        if state.phase == 1 and state.results:
            raise RuntimeProtocolError("result-mismatch")
        try:
            prior_payload = (
                None
                if state.continuation_ref is None
                else self.operations.load_continuation(_text(state.continuation_ref, "reference", _MAX_REF))
            )
            if prior_payload is not None and not isinstance(prior_payload, PiModelPhaseContinuationPayloadV1):
                raise TypeError
            prior = b"[]" if prior_payload is None else prior_payload.transcript_json
        except Exception:
            raise RuntimeProtocolError("continuation-load-failed") from None
        if state.results:
            calls = _prior_calls(prior)
            if tuple(result.id for result in state.results) != tuple(identity for identity, _ in calls):
                raise RuntimeProtocolError("result-mismatch")
        try:
            context.heartbeat(details={"phase": "model"})
        except Exception:
            raise RuntimeProtocolError("activity-stale") from None

        def heartbeat() -> None:
            context.heartbeat(details={"phase": "model"})

        return self._execute(
            state,
            operation,
            prior,
            heartbeat,
        )

    def _execute(  # noqa: C901
        self, state: LoopState, operation: str, prior: bytes, heartbeat: Callable[[], None]
    ) -> object:
        materialization = client = root = identity = None
        clean = True
        ids = {x: f"{operation}.{x}" for x in ("materialize", "admit", "release")}
        try:
            materialization = self.custody.materialize(
                self.connection.identity.connection_id,
                self.config.host_id,
                mode=LeaseMode.READ,
                ttl=self.config.timeout,
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
                self.connection.identity.connection_id,
                self.config.host_id,
                self.connection.authority_epoch,
                self.connection.state_version,
            ):
                raise RuntimeProtocolError("custody-state-mismatch")
            credential = materialization.home.read()
            try:
                key = _text(credential.decode("utf-8", "strict"), "credential", _MAX_KEY)
            except Exception:
                raise RuntimeProtocolError("credential-invalid") from None
            root = Path(mkdtemp(prefix="phase-", dir=self.config.runtime_root))
            os.chmod(root, 0o700)
            metadata = root.lstat()
            if (
                metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o700
                or stat.S_ISLNK(metadata.st_mode)
            ):
                raise RuntimeProtocolError("private-root-invalid")
            identity = (metadata.st_dev, metadata.st_ino)
            calls = _prior_calls(prior) if state.results else ()
            results = [
                {"id": result.id, "method": method, "result": result.to_model_data()}
                for result, (_, method) in zip(state.results, calls, strict=True)
            ]
            frame: dict[str, object] = {
                "type": "start",
                "version": 1,
                "provider": self.config.provider,
                "model": self.config.model,
                "api_key": key,
                "system": self.config.system_prompt,
                "observation": self.config.observation if state.phase == 1 else None,
                "transcript": base64.b64encode(prior).decode(),
                "results": results,
                "limits": _LIMITS,
            }
            client = self.factory.create(
                node=self.node,
                helper=Path(__file__).with_name("pi_model_phase_helper.mjs"),
                entrypoint=self.sdk_entrypoint,
                private_root=root,
            )
            candidate = client.run(frame, self.config.timeout, heartbeat)
            clean = client.close() and clean
            client = None
            clean = _remove(root, identity) and clean
            root = None
            if not clean:
                raise RuntimeProtocolError("cleanup-unverified")
            assistant, transcript, proposals, stop = _validate_candidate(
                prior,
                candidate,
                state,
                self.config.observation,
                self.config.provider,
                self.config.model,
            )
            admission = self.custody.admit_result(fence, operation_id=ids["admit"])
            if not isinstance(admission, AdmissionResult) or (
                admission.operation_id,
                admission.attachment_id,
                admission.purpose,
            ) != (ids["admit"], fence.attachment_id, "result"):
                raise RuntimeProtocolError("custody-admission-mismatch")
            # Release authority before publishing either private value.
            release = self.custody.release(materialization, operation_id=ids["release"])
            materialization = None
            if not _release_verified(release, ids["release"], fence.attachment_id):
                raise RuntimeProtocolError("cleanup-unverified")
            publication = self.operations.publish(
                operation,
                PiModelPhaseOutputPayloadV1(assistant),
                PiModelPhaseContinuationPayloadV1(transcript),
            )
            if not isinstance(publication, PiModelPhasePublication):
                raise RuntimeProtocolError("publication-mismatch")
            return ModelSettlement(
                state,
                stop,
                sha256(assistant).hexdigest(),
                publication.output_reference,
                publication.continuation_reference,
                proposals,
            ).to_data()
        except RuntimeProtocolError:
            raise
        except Exception:
            raise RuntimeProtocolError("runtime-failed") from None
        finally:
            if client is not None:
                clean = client.close() and clean
            if root is not None:
                clean = _remove(root, identity) and clean
            if materialization is not None:
                try:
                    clean = (
                        _release_verified(
                            self.custody.release(materialization, operation_id=ids["release"]),
                            ids["release"],
                            materialization.fence.attachment_id,
                        )
                        and clean
                    )
                except Exception:
                    clean = False
            if not clean:
                raise RuntimeProtocolError("cleanup-unverified")


def _decode(value: object, maximum: int, label: str) -> bytes:
    if not isinstance(value, str):
        raise RuntimeProtocolError("malformed-complete")
    try:
        body = base64.b64decode(value, validate=True)
    except Exception:
        raise RuntimeProtocolError("malformed-complete") from None
    if base64.b64encode(body).decode() != value:
        raise RuntimeProtocolError("malformed-complete")
    try:
        return _payload(body, maximum, label)
    except Exception:
        raise RuntimeProtocolError("malformed-complete") from None


def _prior_calls(prior: bytes) -> tuple[tuple[str, str], ...]:
    messages = cast(list[dict[str, object]], _strict(prior))
    final = messages[-1] if messages else None
    if type(final) is not dict or final.get("role") != "assistant" or type(final.get("content")) is not list:
        raise RuntimeProtocolError("result-mismatch")
    content = cast(list[object], final["content"])
    calls = [item for item in content if type(item) is dict and item.get("type") == "toolCall"]
    identities_and_methods: list[tuple[str, str]] = []
    for call in calls:
        call_data = cast(dict[str, object], call)
        if (
            not {"type", "id", "name", "arguments"}.issubset(call_data)
            or not isinstance(call_data["id"], str)
            or not isinstance(call_data["name"], str)
            or type(call_data["arguments"]) is not dict
        ):
            raise RuntimeProtocolError("result-mismatch")
        identities_and_methods.append((call_data["id"], call_data["name"]))
    return tuple(identities_and_methods)


def _validate_candidate(  # noqa: C901 - exact public assistant and Continuation boundary
    prior: bytes,
    candidate: _Candidate,
    state: LoopState,
    observation: str,
    provider: str,
    model: str,
) -> tuple[bytes, bytes, tuple[Proposal, ...], StopReason]:
    try:
        assistant = cast(dict[str, object], _strict(_payload(candidate.assistant, MAX_OUTPUT_BYTES, "assistant")))
        transcript = cast(list[object], _strict(_payload(candidate.transcript, MAX_TRANSCRIPT_BYTES, "transcript")))
    except Exception:
        raise RuntimeProtocolError("malformed-complete") from None
    old = cast(list[object], _strict(prior))
    expected = list(old)
    if state.phase == 1:
        expected.append({"role": "user", "content": [{"type": "text", "text": observation}], "timestamp": 0})
    if state.results:
        calls = _prior_calls(prior)
        if len(calls) != len(state.results):
            raise RuntimeProtocolError("result-mismatch")
        for result, (identity, method) in zip(state.results, calls, strict=True):
            if result.id != identity:
                raise RuntimeProtocolError("result-mismatch")
            expected.append(
                {
                    "role": "toolResult",
                    "toolCallId": result.id,
                    "toolName": method,
                    "content": [{"type": "text", "text": json.dumps(result.to_model_data(), separators=(",", ":"))}],
                    "isError": not result.ok,
                    "timestamp": 0,
                }
            )
    expected.append(assistant)
    if transcript != expected or transcript[-1] != assistant:
        raise RuntimeProtocolError("transcript-mismatch")
    required_assistant = {"role", "content", "api", "provider", "model", "usage", "stopReason", "timestamp"}
    optional_assistant = {
        "responseModel",
        "responseId",
        "diagnostics",
        "errorMessage",
        "rawStopReason",
    }
    if (
        assistant.get("role") != "assistant"
        or type(assistant.get("content")) is not list
        or not required_assistant.issubset(assistant)
        or set(assistant) - required_assistant - optional_assistant
        or assistant.get("provider") != provider
        or assistant.get("model") != model
        or not _assistant_metadata(assistant)
    ):
        raise RuntimeProtocolError("malformed-complete")
    try:
        stop = StopReason(assistant.get("stopReason"))
    except ValueError, TypeError:
        raise RuntimeProtocolError("malformed-complete") from None
    proposals = []
    for block in cast(list[object], assistant["content"]):
        if not _content_block(block):
            raise RuntimeProtocolError("malformed-complete")
        if cast(dict[str, object], block).get("type") == "toolCall":
            block_data = cast(dict[str, object], block)
            if (
                not {"type", "id", "name", "arguments"}.issubset(block_data)
                or set(block_data) - {"type", "id", "name", "arguments", "thoughtSignature"}
                or not isinstance(block_data["id"], str)
                or not isinstance(block_data["name"], str)
                or type(block_data["arguments"]) is not dict
                or ("thoughtSignature" in block_data and not isinstance(block_data["thoughtSignature"], str))
            ):
                raise RuntimeProtocolError("malformed-proposal")
            try:
                proposals.append(
                    Proposal(
                        block_data["id"],
                        block_data["name"],
                        cast(dict[str, object], block_data["arguments"]),
                    )
                )
            except Exception:
                raise RuntimeProtocolError("malformed-proposal") from None
    if len(proposals) > MAX_PROPOSALS:
        raise RuntimeProtocolError("proposal-overflow")
    if len({proposal.id for proposal in proposals}) != len(proposals):
        raise RuntimeProtocolError("malformed-proposal")
    return candidate.assistant, candidate.transcript, tuple(proposals), stop


def _assistant_metadata(value: dict[str, object]) -> bool:
    usage = value.get("usage")
    if not _usage_metadata(usage):
        return False
    timestamp = value.get("timestamp")
    if isinstance(timestamp, bool) or not isinstance(timestamp, int | float) or not math.isfinite(timestamp):
        return False
    for name in ("api", "provider", "model"):
        try:
            _text(value.get(name), f"assistant {name}")
        except ValueError:
            return False
    for name in ("responseModel", "responseId", "errorMessage", "rawStopReason"):
        if name in value and not isinstance(value[name], str):
            return False
    return "diagnostics" not in value or isinstance(value["diagnostics"], list)


def _usage_metadata(usage: object) -> bool:
    if type(usage) is not dict or set(usage) - {
        "input",
        "output",
        "cacheRead",
        "cacheWrite",
        "cacheWrite1h",
        "reasoning",
        "totalTokens",
        "cost",
    }:
        return False
    required = {"input", "output", "cacheRead", "cacheWrite", "totalTokens", "cost"}
    if not required.issubset(usage):
        return False
    cost = usage.get("cost")
    if type(cost) is not dict or set(cost) != {"input", "output", "cacheRead", "cacheWrite", "total"}:
        return False
    numbers = [item for key, item in usage.items() if key != "cost"] + list(cost.values())
    return not any(
        isinstance(item, bool) or not isinstance(item, int | float) or not math.isfinite(item) or item < 0
        for item in numbers
    )


def _content_block(value: object) -> bool:
    if type(value) is not dict or not isinstance(value.get("type"), str):
        return False
    block = cast(dict[str, object], value)
    if block["type"] == "text":
        return (
            set(block) <= {"type", "text", "textSignature"}
            and isinstance(block.get("text"), str)
            and ("textSignature" not in block or isinstance(block["textSignature"], str))
        )
    if block["type"] == "thinking":
        return (
            set(block) <= {"type", "thinking", "thinkingSignature", "redacted"}
            and isinstance(block.get("thinking"), str)
            and ("thinkingSignature" not in block or isinstance(block["thinkingSignature"], str))
            and ("redacted" not in block or type(block["redacted"]) is bool)
        )
    return block["type"] == "toolCall"


def _release_verified(value: object, operation: str, attachment: str) -> bool:
    return (
        isinstance(value, ReleaseResult)
        and value.operation_id == operation
        and isinstance(value.cleanup, CleanupEvidence)
        and value.cleanup.attachment_id == attachment
        and (value.cleanup.removed or value.cleanup.already_absent)
        and not value.cleanup.security_violation
    )


def _remove(root: Path, identity: tuple[int, int] | None) -> bool:
    try:
        info = root.lstat()
    except FileNotFoundError:
        return True
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
        or identity != (info.st_dev, info.st_ino)
    ):
        return False
    try:
        shutil.rmtree(root)
    except OSError:
        return False
    return not os.path.lexists(root)
