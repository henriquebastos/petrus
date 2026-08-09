"""Private host-local process bridge for the qualified Codex Gondolin lane."""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import socket
import sqlite3
import stat
import threading
from pathlib import Path
from typing import TYPE_CHECKING, cast

from petrus.agenticus.runtime.codex import CodexGondolinRuntimeAdapter, CodexRuntimeInvocation
from petrus.agenticus.runtime.operation import (
    RuntimeCleanupDisposition,
    RuntimeOperationCleanup,
    RuntimeProtocolError,
)
from petrus.agenticus.runtime.result import RuntimeTurnSettlement
from petrus.agenticus.thread.continuation import Continuation
from petrus.agenticus.thread.identity import EpisodeId, TurnId
from petrus.agenticus.thread.lifecycle import TurnOutcome
from petrus.motus.activity import ActivityInvocation

if TYPE_CHECKING:
    from petrus.agenticus.attachment.episode import EpisodeAttachment
    from petrus.agenticus.connection.custody import ConnectionView
    from petrus.motus.activity import ActivityExecutionContext

_ACTIVITY = "agenticus.codex.a3.gondolin"
_ENDPOINT_ENV = "PETRUS_CODEX_GONDOLIN_ENDPOINT"
_TOKEN_ENV = "PETRUS_CODEX_GONDOLIN_TOKEN"
_MAX_REQUEST = 64 * 1024
_MAX_RESPONSE = 16 * 1024
_FRAME_TIMEOUT = 1.0
_CLOSE_TIMEOUT = 2.0
_SCHEMA_VERSION = 1
_DDL = """CREATE TABLE operations (
 operation_id TEXT PRIMARY KEY NOT NULL,
 request_fingerprint TEXT NOT NULL
  CHECK(length(request_fingerprint)=64 AND request_fingerprint NOT GLOB '*[^0-9a-f]*'),
 phase TEXT NOT NULL CHECK(phase IN ('executing','terminal')),
 terminal BLOB,
 episode_id TEXT NOT NULL, turn_id TEXT NOT NULL,
 CHECK((phase='executing' AND terminal IS NULL) OR (phase='terminal' AND terminal IS NOT NULL)))"""
_ERRORS = frozenset(
    {
        "unauthorized",
        "frame-too-large",
        "request-invalid",
        "operation-conflict",
        "operation-indeterminate",
        "runtime-failed",
    }
)
_TERMINAL_RESULT_FIELDS = frozenset(
    {
        "version",
        "operation_id",
        "episode_id",
        "turn_id",
        "outcome",
        "accepted_appends",
        "termination_code",
        "output_reference",
        "continuation_reference",
        "cleanup",
    }
)


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _terminal_error(code: str) -> dict[str, object]:
    return {"ok": False, "error": code}


def _bounded_string(value: object, *, nullable: bool = False) -> bool:
    return (nullable and value is None) or (type(value) is str and 0 < len(value) <= 4096)


def _parse_terminal(  # noqa: C901 -- exact closed protocol validation is intentionally one home
    encoded: bytes,
    *,
    operation_id: str | None = None,
    episode_id: EpisodeId | None = None,
    turn_id: TurnId | None = None,
) -> dict[str, object]:
    """Parse the one closed, canonical terminal wire value used at every boundary."""
    if not encoded.endswith(b"\n") or encoded.count(b"\n") != 1 or len(encoded) > _MAX_RESPONSE:
        raise ValueError("terminal frame shape")
    try:
        value = json.loads(encoded[:-1])
    except UnicodeDecodeError, json.JSONDecodeError, RecursionError:
        raise ValueError("terminal JSON") from None
    try:
        canonical = _json_bytes(value) + b"\n"
    except TypeError, ValueError, RecursionError:
        raise ValueError("terminal canonical form") from None
    if canonical != encoded or not isinstance(value, dict):
        raise ValueError("terminal canonical form")
    terminal = cast(dict[str, object], value)
    if terminal.get("ok") is False:
        if (
            set(terminal) != {"ok", "error"}
            or type(terminal.get("error")) is not str
            or terminal["error"] not in _ERRORS
        ):
            raise ValueError("terminal error")
        return terminal
    if terminal.get("ok") is not True or set(terminal) != {"ok", "result"} or not isinstance(terminal["result"], dict):
        raise ValueError("terminal envelope")
    result = cast(dict[str, object], terminal["result"])
    cleanup = result.get("cleanup")
    if (
        set(result) != _TERMINAL_RESULT_FIELDS
        or not isinstance(cleanup, dict)
        or set(cleanup) != {"disposition", "code"}
    ):
        raise ValueError("terminal result shape")
    cleanup = cast(dict[str, object], cleanup)
    if type(result["version"]) is not int or result["version"] != 1:
        raise ValueError("terminal version")
    if not all(
        _bounded_string(result[field]) for field in ("operation_id", "episode_id", "turn_id", "termination_code")
    ):
        raise ValueError("terminal identity")
    if not _bounded_string(result["output_reference"], nullable=True) or not _bounded_string(
        result["continuation_reference"], nullable=True
    ):
        raise ValueError("terminal references")
    if type(result["accepted_appends"]) is not int or result["accepted_appends"] not in (0, 1):
        raise ValueError("terminal appends")
    try:
        parsed_episode, parsed_turn = EpisodeId.from_data(result["episode_id"]), TurnId.from_data(result["turn_id"])
        settlement = RuntimeTurnSettlement(
            parsed_episode,
            parsed_turn,
            TurnOutcome(cast(str, result["outcome"])),
            cast(int, result["accepted_appends"]),
            cast(str, result["termination_code"]),
            cast(str | None, result["output_reference"]),
            cast(str | None, result["continuation_reference"]),
        )
        RuntimeOperationCleanup(
            cast(str, result["operation_id"]),
            RuntimeCleanupDisposition(cast(str, cleanup["disposition"])),
            cast(str, cleanup["code"]),
        )
    except TypeError, ValueError:
        raise ValueError("terminal domain") from None
    if type(cleanup["code"]) is not str or not _bounded_string(cleanup["code"]):
        raise ValueError("terminal cleanup")
    if operation_id is not None and result["operation_id"] != operation_id:
        raise ValueError("terminal operation correlation")
    if episode_id is not None and settlement.episode_id != episode_id:
        raise ValueError("terminal episode correlation")
    if turn_id is not None and settlement.turn_id != turn_id:
        raise ValueError("terminal turn correlation")
    return terminal


class _CodexGondolinRuntimeService:
    """Borrow one pre-provisioned Attachment behind one process-safe service fence."""

    def __init__(
        self,
        endpoint: Path,
        ledger: Path,
        token: str,
        adapter: CodexGondolinRuntimeAdapter,
        connection: ConnectionView,
        attachment: EpisodeAttachment,
    ) -> None:
        from petrus.agenticus.attachment.episode import EpisodeAttachment
        from petrus.agenticus.connection.custody import ConnectionStatus, ConnectionView

        if not isinstance(adapter, CodexGondolinRuntimeAdapter):
            raise TypeError("service requires the exact Codex Gondolin runtime adapter")
        if not isinstance(connection, ConnectionView) or connection.status is not ConnectionStatus.READY:
            raise ValueError("service requires one ready connection")
        if not isinstance(attachment, EpisodeAttachment):
            raise TypeError("service requires one existing Episode Attachment")
        if type(token) is not str or not 32 <= len(token) <= 256 or not token.isascii() or not token.isprintable():
            raise ValueError("service token must contain 32..256 printable ASCII characters")
        self._endpoint, self._ledger, self._token = Path(endpoint), Path(ledger), token
        if self._endpoint.parent != self._ledger.parent:
            raise ValueError("service endpoint and ledger require one state directory")
        self._adapter, self._connection, self._attachment = adapter, connection, attachment
        self._stop, self._execution_lock = threading.Event(), threading.Lock()
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._lock_file = None
        self._pid = os.getpid()
        self._acquire_fence()
        try:
            self._initialize_ledger()
        except BaseException:
            self._release_fence()
            raise

    def _acquire_fence(self) -> None:
        state = self._endpoint.parent
        if state.is_symlink():
            raise RuntimeError("runtime-service-state-invalid")
        state.mkdir(parents=True, mode=0o700, exist_ok=True)
        metadata = state.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_uid != os.geteuid()
        ):
            raise RuntimeError("runtime-service-state-invalid")
        lock = state / ".service.lock"
        descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        lock_metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(lock_metadata.st_mode)
            or stat.S_IMODE(lock_metadata.st_mode) != 0o600
            or lock_metadata.st_uid != os.geteuid()
        ):
            os.close(descriptor)
            raise RuntimeError("runtime-service-state-invalid")
        file = os.fdopen(descriptor, "r+b", buffering=0)
        try:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            file.close()
            raise RuntimeError("runtime-service-owned") from None
        self._lock_file = file

    def _release_fence(self) -> None:
        if self._lock_file is not None:
            if os.getpid() == self._pid:
                fcntl.flock(self._lock_file, fcntl.LOCK_UN)
            self._lock_file.close()
            self._lock_file = None

    def _ensure_owner(self) -> None:
        if os.getpid() != self._pid or self._lock_file is None:
            raise RuntimeError("runtime-service-owner-invalid")

    def _connect_db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self._ledger, timeout=2)
        if db.execute("PRAGMA journal_mode=WAL").fetchone() != ("wal",):
            db.close()
            raise RuntimeError("runtime-service-storage-failed")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def _initialize_ledger(self) -> None:
        try:
            try:
                metadata = self._ledger.lstat()
                created = False
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or stat.S_IMODE(metadata.st_mode) != 0o600
                    or metadata.st_uid != os.geteuid()
                ):
                    raise RuntimeError
            except FileNotFoundError:
                descriptor = os.open(
                    self._ledger,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                )
                os.close(descriptor)
                created = True
            with self._connect_db() as db:
                if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise RuntimeError
                if created:
                    db.execute(_DDL)
                    db.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
                self._validate_ledger(db)
                indeterminate = _json_bytes(_terminal_error("operation-indeterminate"))
                db.execute(
                    "UPDATE operations SET phase='terminal', terminal=? WHERE phase='executing'", (indeterminate,)
                )
        except OSError, sqlite3.Error, TypeError, ValueError, RuntimeError:
            raise RuntimeError("runtime-service-storage-failed") from None

    @staticmethod
    def _validate_ledger(db: sqlite3.Connection) -> None:
        columns = [(row[1], row[2], row[3], row[5]) for row in db.execute("PRAGMA table_info(operations)")]
        expected = [
            ("operation_id", "TEXT", 1, 1),
            ("request_fingerprint", "TEXT", 1, 0),
            ("phase", "TEXT", 1, 0),
            ("terminal", "BLOB", 0, 0),
            ("episode_id", "TEXT", 1, 0),
            ("turn_id", "TEXT", 1, 0),
        ]
        stored_ddl = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='operations'").fetchone()

        def normalize(value: str) -> str:
            return re.sub(r"\s+", " ", value.strip()).lower()

        if (
            db.execute("PRAGMA user_version").fetchone() != (_SCHEMA_VERSION,)
            or columns != expected
            or stored_ddl is None
            or normalize(stored_ddl[0]) != normalize(_DDL)
        ):
            raise RuntimeError
        rows = db.execute(
            "SELECT operation_id,request_fingerprint,phase,terminal,episode_id,turn_id FROM operations"
        ).fetchall()
        for operation_id, fingerprint, phase, terminal, episode, turn in rows:
            if (
                not all(type(value) is str and value for value in (operation_id, fingerprint, phase, episode, turn))
                or re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None
            ):
                raise RuntimeError
            parsed_episode, parsed_turn = EpisodeId.from_data(episode), TurnId.from_data(turn)
            if phase == "terminal":
                _parse_terminal(
                    bytes(terminal) + b"\n",
                    operation_id=operation_id,
                    episode_id=parsed_episode,
                    turn_id=parsed_turn,
                )
            elif phase != "executing" or terminal is not None:
                raise RuntimeError

    def start(self) -> None:
        self._ensure_owner()
        if self._thread is not None:
            raise RuntimeError("service already started")
        try:
            endpoint = self._endpoint.lstat()
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISSOCK(endpoint.st_mode):
                raise RuntimeError("runtime-service-endpoint-invalid")
            self._endpoint.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self._endpoint))
            os.chmod(self._endpoint, 0o600)
            server.listen(8)
            server.settimeout(0.1)
        except BaseException:
            server.close()
            raise
        self._socket = server
        self._thread = threading.Thread(target=self._serve, name="codex-gondolin-runtime-service", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._ensure_owner()
        self._stop.set()
        if self._socket is not None:
            self._socket.close()
        if self._thread is not None:
            self._thread.join(_CLOSE_TIMEOUT)
            if self._thread.is_alive():
                raise RuntimeError("runtime-service-quiescence-failed")
        try:
            if stat.S_ISSOCK(self._endpoint.lstat().st_mode):
                self._endpoint.unlink()
        except FileNotFoundError:
            pass
        self._release_fence()

    def _serve(self) -> None:
        assert self._socket is not None
        while not self._stop.is_set():
            try:
                client, _ = self._socket.accept()
            except TimeoutError, OSError:
                continue
            self._handle(client)

    def _handle(self, client: socket.socket) -> None:
        with client:
            client.settimeout(_FRAME_TIMEOUT)
            try:
                frame = b""
                while b"\n" not in frame and len(frame) <= _MAX_REQUEST:
                    chunk = client.recv(min(4096, _MAX_REQUEST + 1 - len(frame)))
                    if not chunk:
                        break
                    frame += chunk
                if len(frame) > _MAX_REQUEST:
                    response = _terminal_error("frame-too-large")
                elif not frame.endswith(b"\n") or frame.count(b"\n") != 1:
                    response = _terminal_error("request-invalid")
                else:
                    response = self._request(frame[:-1])
            except OSError, TimeoutError:
                response = _terminal_error("request-invalid")
            except Exception:
                response = _terminal_error("runtime-failed")
            encoded = _json_bytes(response) + b"\n"
            try:
                _parse_terminal(encoded)
            except ValueError:
                encoded = _json_bytes(_terminal_error("runtime-failed")) + b"\n"
            try:
                client.sendall(encoded)
            except OSError:
                pass

    def _request(self, frame: bytes) -> dict[str, object]:  # noqa: C901 -- one bounded admission door
        try:
            value = json.loads(frame)
            canonical_frame = _json_bytes(value)
        except UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError:
            return _terminal_error("request-invalid")
        if (
            canonical_frame != frame
            or not isinstance(value, dict)
            or set(value) != {"version", "token", "operation_id", "input"}
        ):
            return _terminal_error("request-invalid")
        request = cast(dict[str, object], value)
        supplied = request["token"]
        if (
            type(supplied) is not str
            or not supplied.isascii()
            or len(supplied) > 256
            or not hmac.compare_digest(supplied, self._token)
        ):
            return _terminal_error("unauthorized")
        if type(request["version"]) is not int or request["version"] != 1 or type(request["operation_id"]) is not str:
            return _terminal_error("request-invalid")
        operation_id = request["operation_id"]
        if not operation_id or len(operation_id) > 256:
            return _terminal_error("request-invalid")
        canonical = _json_bytes({"version": 1, "operation_id": operation_id, "input": request["input"]})
        fingerprint = hashlib.sha256(canonical).hexdigest()
        try:
            invocation = self._runtime_invocation(operation_id, request["input"])
        except Exception:
            return _terminal_error("request-invalid")
        with self._execution_lock:
            try:
                with self._connect_db() as db:
                    row = db.execute(
                        "SELECT request_fingerprint,phase,terminal FROM operations WHERE operation_id=?",
                        (operation_id,),
                    ).fetchone()
                    if row is not None:
                        if row[0] != fingerprint:
                            return _terminal_error("operation-conflict")
                        if row[1] != "terminal":
                            return _terminal_error("operation-indeterminate")
                        return _parse_terminal(
                            bytes(row[2]) + b"\n",
                            operation_id=operation_id,
                            episode_id=invocation.episode_id,
                            turn_id=invocation.turn_id,
                        )
                    db.execute(
                        "INSERT INTO operations VALUES(?,?,'executing',NULL,?,?)",
                        (operation_id, fingerprint, invocation.episode_id.to_data(), invocation.turn_id.to_data()),
                    )
            except sqlite3.Error, ValueError, TypeError:
                return _terminal_error("runtime-failed")
            terminal = self._execute(invocation)
            encoded = _json_bytes(terminal)
            try:
                _parse_terminal(
                    encoded + b"\n",
                    operation_id=operation_id,
                    episode_id=invocation.episode_id,
                    turn_id=invocation.turn_id,
                )
                with self._connect_db() as db:
                    cursor = db.execute(
                        "UPDATE operations SET phase='terminal',terminal=? WHERE operation_id=? AND phase='executing'",
                        (encoded, operation_id),
                    )
                    if cursor.rowcount != 1:
                        raise sqlite3.DatabaseError
            except sqlite3.Error, ValueError, TypeError:
                return _terminal_error("runtime-failed")
            return terminal

    def _runtime_invocation(self, operation_id: str, value: object) -> CodexRuntimeInvocation:
        fields = {
            "version",
            "episode_id",
            "turn_id",
            "prompt",
            "attachment_id",
            "attachment_epoch",
            "connection_id",
            "authority_epoch",
            "state_version",
            "continuation",
        }
        if not isinstance(value, dict) or set(value) != fields:
            raise ValueError
        data = cast(dict[str, object], value)
        if type(data["version"]) is not int or data["version"] != 1 or type(data["prompt"]) is not str:
            raise ValueError
        for field in ("attachment_id", "connection_id"):
            if type(data[field]) is not str:
                raise ValueError
        for field in ("attachment_epoch", "authority_epoch", "state_version"):
            if type(data[field]) is not int or cast(int, data[field]) <= 0:
                raise ValueError
        episode_id, turn_id = EpisodeId.from_data(data["episode_id"]), TurnId.from_data(data["turn_id"])
        continuation = None if data["continuation"] is None else Continuation.from_data(data["continuation"])
        coordinates = self._attachment.coordinates()
        if (
            episode_id != self._attachment.episode_id
            or data["attachment_id"] != coordinates.attachment_id
            or data["attachment_epoch"] != coordinates.attachment_epoch
            or data["connection_id"] != self._connection.identity.connection_id
            or data["authority_epoch"] != self._connection.authority_epoch
            or data["state_version"] != self._connection.state_version
        ):
            raise ValueError
        return CodexRuntimeInvocation(
            operation_id, episode_id, turn_id, data["prompt"], self._connection, self._attachment, continuation
        )

    def _execute(self, invocation: CodexRuntimeInvocation) -> dict[str, object]:
        operation = None
        operation_closed = False
        try:
            operation = self._adapter.start(invocation)
            result = operation.wait()
            cleanup = operation.close()
            operation_closed = True
            terminal = {
                "ok": True,
                "result": {
                    "version": 1,
                    "operation_id": operation.operation_id,
                    "episode_id": result.episode_id.to_data(),
                    "turn_id": result.turn_id.to_data(),
                    "outcome": result.outcome.value,
                    "accepted_appends": result.accepted_appends,
                    "termination_code": result.termination_code,
                    "output_reference": result.output_reference,
                    "continuation_reference": result.continuation_reference,
                    "cleanup": {"disposition": cleanup.disposition.value, "code": cleanup.code},
                },
            }
            return _parse_terminal(
                _json_bytes(terminal) + b"\n",
                operation_id=invocation.operation_id,
                episode_id=invocation.episode_id,
                turn_id=invocation.turn_id,
            )
        except Exception:
            return _terminal_error("runtime-failed")
        finally:
            if operation is not None and not operation_closed:
                try:
                    operation.close()
                except Exception:
                    pass


class _CodexGondolinActivityClient:
    """Reconstructible Worker-side Activity using only process configuration."""

    def __call__(  # noqa: C901 -- socket custody and heartbeat failure ordering stay visible together
        self, invocation: ActivityInvocation, *, context: ActivityExecutionContext
    ) -> object:
        if type(invocation.activity) is not str or invocation.activity != _ACTIVITY:
            raise RuntimeProtocolError("activity-mismatch")
        if type(invocation.idempotency) is not str:
            raise RuntimeProtocolError("idempotency-required")
        endpoint, token = os.environ.get(_ENDPOINT_ENV), os.environ.get(_TOKEN_ENV)
        if not endpoint or not token or not 32 <= len(token) <= 256 or not token.isascii() or not token.isprintable():
            raise RuntimeProtocolError("runtime-service-unavailable")
        try:
            context.heartbeat(details={"phase": "runtime"})
        except Exception:
            raise RuntimeProtocolError("activity-stale") from None
        request = {"version": 1, "token": token, "operation_id": invocation.idempotency, "input": invocation.input}
        try:
            if not isinstance(invocation.input, dict):
                raise ValueError
            input_value = cast(dict[str, object], invocation.input)
            expected_episode = EpisodeId.from_data(input_value["episode_id"])
            expected_turn = TurnId.from_data(input_value["turn_id"])
            encoded = _json_bytes(request) + b"\n"
        except KeyError, TypeError, ValueError, RecursionError:
            raise RuntimeProtocolError("input-invalid") from None
        if len(encoded) > _MAX_REQUEST:
            raise RuntimeProtocolError("request-too-large")
        interval = min(0.25, invocation.policy.heartbeat_timeout / 3)
        response = b""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(interval)
                client.connect(endpoint)
                client.sendall(encoded)
                while b"\n" not in response and len(response) <= _MAX_RESPONSE:
                    try:
                        chunk = client.recv(min(4096, _MAX_RESPONSE + 1 - len(response)))
                    except TimeoutError:
                        try:
                            context.heartbeat(details={"phase": "runtime"})
                        except Exception:
                            client.close()
                            raise RuntimeProtocolError("activity-stale") from None
                        continue
                    if not chunk:
                        break
                    response += chunk
        except RuntimeProtocolError:
            raise
        except Exception:
            raise RuntimeProtocolError("runtime-service-unavailable") from None
        try:
            value = _parse_terminal(
                response,
                operation_id=invocation.idempotency,
                episode_id=expected_episode,
                turn_id=expected_turn,
            )
        except ValueError:
            raise RuntimeProtocolError("runtime-service-failed") from None
        if value["ok"] is not True:
            raise RuntimeProtocolError(cast(str, value["error"]))
        return cast(dict[str, object], value["result"])


__all__: list[str] = []
