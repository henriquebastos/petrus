"""One common capability-scoped gateway path for every version-1 Hands call.

Every request follows request -> direct precheck -> adapter/stage ->
serialized postcheck -> commit/discard -> exact result. Prechecks run before
any adapter or provider crossing and leave adapter, stage, commit, and target
counters flat. The postcheck and each commit run under the barrier shared with
attachment transition and cleanup, so a transition can never advance while a
commit is active and a staged write can never commit past the fence.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import Condition, RLock
from types import MappingProxyType
from typing import Protocol, TypeGuard

from petrus.agenticus.hands.contract import (
    MAX_DATA_TEXT_BYTES,
    ReadParams,
    RejectionCategory,
    SearchParams,
    ShellParams,
    ToolError,
    ToolCallConflict,
    ToolMethod,
    ToolRequest,
    ToolRequestRejected,
    ToolResult,
    WriteParams,
    parse_tool_request,
)
from petrus.agenticus.hands.grants import CapabilityGrant, GrantBudgetExhausted, GrantLedger, GrantLedgerError

_UNPARSED_CALL_ID = "unparsed-request"
_MAX_SEARCH_RESULTS = 64
_MAX_IDENTITY_BYTES = 256


def _bounded_value(value: object, name: str, *, empty: bool = True, controls: bool = False) -> str:
    if (
        not isinstance(value, str)
        or (not empty and not value)
        or len(value.encode()) > MAX_DATA_TEXT_BYTES
        or (not controls and any(ord(character) < 32 for character in value))
    ):
        raise ValueError(f"{name} must be a bounded string without control characters")
    return value


def _identity(value: object, name: str) -> str:
    value = _bounded_value(value, name, empty=False)
    if len(value.encode()) > _MAX_IDENTITY_BYTES:
        raise ValueError(f"{name} must be a bounded identity string")
    return value


def _digest_value(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True)
class ShellOutcome:
    """Bounded, provider-neutral process outcome; never raw provider state."""

    returncode: int
    stdout: str
    stderr: str
    truncated: bool

    def __post_init__(self) -> None:
        if type(self.returncode) is not int:
            raise TypeError("shell outcome returncode must be an integer")
        _bounded_value(self.stdout, "shell outcome stdout", controls=True)
        _bounded_value(self.stderr, "shell outcome stderr", controls=True)
        if type(self.truncated) is not bool:
            raise TypeError("shell outcome truncated must be a boolean")


@dataclass(frozen=True)
class StagedWrite:
    """One authoritative stage token; the stage lives outside every final target."""

    call_id: str
    path: str
    digest: str

    def __post_init__(self) -> None:
        _bounded_value(self.call_id, "staged write call_id", empty=False)
        _bounded_value(self.path, "staged write path", empty=False)
        _digest_value(self.digest, "staged write digest")


@dataclass(frozen=True)
class TestOutcome:
    """One fixed-verifier outcome with digest evidence only."""

    passed: bool
    evidence_digest: str

    def __post_init__(self) -> None:
        if type(self.passed) is not bool:
            raise TypeError("test outcome passed must be a boolean")
        _digest_value(self.evidence_digest, "test outcome evidence_digest")


class HandsAdapter(Protocol):
    """Provider-neutral workspace operations behind the gateway.

    Adapters expose authoritative stage/commit/discard operations and bounded
    digest or text evidence. They never expose raw provider state, sessions,
    credentials, or unbounded output.
    """

    def read(self, path: str) -> str: ...

    def search(self, query: str, path: str) -> tuple[str, ...]: ...

    def shell(self, argv: tuple[str, ...], cwd: str) -> ShellOutcome: ...

    def stage_write(self, call_id: str, path: str, content: str) -> StagedWrite: ...

    def commit_write(self, staged: StagedWrite) -> str: ...

    def discard_write(self, staged: StagedWrite) -> None: ...

    def run_test(self) -> TestOutcome: ...

    def discard_all_stages(self) -> int: ...


@dataclass(frozen=True)
class CallFence:
    """One snapshot of the dynamic attachment state a call must satisfy."""

    open: bool
    aborted: bool
    deadline: float

    def __post_init__(self) -> None:
        if type(self.open) is not bool or type(self.aborted) is not bool:
            raise TypeError("call fence states must be booleans")
        if (
            isinstance(self.deadline, bool)
            or not isinstance(self.deadline, int | float)
            or not math.isfinite(self.deadline)
        ):
            raise ValueError("call fence deadline must be a finite number")


class CallFenceSource(Protocol):
    """The current attachment gate; refreshed again under the barrier."""

    def snapshot(self) -> CallFence: ...


class ResultAdmission(Protocol):
    """DS2 admission seam; a stale, revoked, or removed fence returns False."""

    def admit(self, call_id: str) -> bool: ...


class TargetCurrency(Protocol):
    """Host target-head seam consulted under the barrier before a write commit."""

    def is_current(self) -> bool: ...


@dataclass(frozen=True)
class CallEvidence:
    """One bounded finalized call fact for host sensors; secret-free by shape."""

    sequence: int
    call_id: str
    episode_id: str
    method: ToolMethod | None
    ok: bool
    category: RejectionCategory | None
    epoch: int


@dataclass(frozen=True)
class GatewayCounters:
    """Exact request, rejection, stage, commit, and mutation accounting."""

    requests: int
    rejections: MappingProxyType[str, int]
    adapter_entries: int
    stages: int
    commits: int
    stage_discards: int
    stage_discard_failures: int
    target_mutations: int
    results_admitted: int


class HandsGateway:
    """The single gateway for one Episode Attachment epoch. No local fallback exists."""

    def __init__(
        self,
        *,
        episode_id: str,
        adapter: HandsAdapter,
        grants: GrantLedger,
        fence: CallFenceSource,
        barrier: RLock,
        admission: ResultAdmission | None = None,
        target: TargetCurrency | None = None,
        clock: Callable[[], float] = time.monotonic,
        max_evidence: int = 256,
        max_calls: int = 256,
    ) -> None:
        if type(max_evidence) is not int or max_evidence <= 0:
            raise ValueError("gateway max_evidence must be a positive integer")
        if type(max_calls) is not int or max_calls <= 0:
            raise ValueError("gateway max_calls must be a positive integer")
        self._episode_id = _identity(episode_id, "gateway episode_id")
        self._adapter = adapter
        self._grants = grants
        self._fence = fence
        self._barrier = barrier
        self._admission = admission
        self._target = target
        self._clock = clock
        self._state = Condition()
        self._in_flight = 0
        self._sequence = 0
        self._requests = 0
        self._rejections: dict[str, int] = {}
        self._adapter_entries = 0
        self._stages = 0
        self._commits = 0
        self._stage_discards = 0
        self._stage_discard_failures = 0
        self._target_mutations = 0
        self._results_admitted = 0
        self._evidence: deque[CallEvidence] = deque(maxlen=max_evidence)
        self._max_calls = max_calls
        self._calls: dict[str, tuple[ToolRequest, ToolResult | None]] = {}

    @property
    def attachment_id(self) -> str:
        return self._grants.attachment_id

    @property
    def episode_id(self) -> str:
        return self._episode_id

    @property
    def attachment_epoch(self) -> int:
        return self._grants.attachment_epoch

    def counters(self) -> GatewayCounters:
        with self._state:
            return GatewayCounters(
                requests=self._requests,
                rejections=MappingProxyType(dict(self._rejections)),
                adapter_entries=self._adapter_entries,
                stages=self._stages,
                commits=self._commits,
                stage_discards=self._stage_discards,
                stage_discard_failures=self._stage_discard_failures,
                target_mutations=self._target_mutations,
                results_admitted=self._results_admitted,
            )

    def evidence(self) -> tuple[CallEvidence, ...]:
        with self._state:
            return tuple(self._evidence)

    def drain(self, timeout: float = 30.0) -> bool:
        """Wait until no call is between adapter entry and its finalized result."""

        deadline = self._clock() + timeout
        with self._state:
            while self._in_flight > 0:
                remaining = deadline - self._clock()
                if remaining <= 0 or not self._state.wait(timeout=remaining):
                    return self._in_flight == 0
            return True

    def submit(self, data: object) -> ToolResult:
        """Run one request through the complete common path and return its exact result."""

        with self._state:
            self._requests += 1
        try:
            request = parse_tool_request(data)
        except ToolRequestRejected as rejected:
            return self._reject_unparsed(data, rejected)
        try:
            prior = self._claim(request)
            if prior is not None:
                return prior
            error = self._precheck(request)
            if error is not None:
                return self._terminal(request, error=error)
            try:
                grant = self._grants.consume(request.grant_epoch)
            except GrantBudgetExhausted:
                return self._terminal(request, error=_error(RejectionCategory.BUDGET, "grant call budget is exhausted"))
            except GrantLedgerError:
                return self._terminal(request, error=_error(RejectionCategory.STALE_EPOCH, "grant is not current"))
            result = self._execute(request, grant)
            self._publish(request, result)
            return result
        except BaseException:
            self._abandon(request)
            raise

    def _claim(self, request: ToolRequest) -> ToolResult | None:
        with self._state:
            while True:
                found = self._calls.get(request.call_id)
                if found is None:
                    if len(self._calls) >= self._max_calls:
                        return self._finalize(
                            request, error=_error(RejectionCategory.BUDGET, "call ledger budget is exhausted")
                        )
                    self._calls[request.call_id] = (request, None)
                    # Settlement must drain every claimed call, including one
                    # between its initial fence check and adapter entry.
                    self._in_flight += 1
                    return None
                original, result = found
                if original != request:
                    raise ToolCallConflict
                if result is not None:
                    return result
                self._state.wait()

    def _publish(self, request: ToolRequest, result: ToolResult) -> None:
        with self._state:
            self._calls[request.call_id] = (request, result)
            self._in_flight -= 1
            self._state.notify_all()

    def _terminal(self, request: ToolRequest, *, error: ToolError) -> ToolResult:
        result = self._finalize(request, error=error)
        self._publish(request, result)
        return result

    def _abandon(self, request: ToolRequest) -> None:
        with self._state:
            found = self._calls.get(request.call_id)
            if found is not None and found[0] == request and found[1] is None:
                del self._calls[request.call_id]
                self._in_flight -= 1
                self._state.notify_all()

    def _precheck(self, request: ToolRequest) -> ToolError | None:
        """Direct prechecks; adapter, stage, commit, and target counters stay flat."""

        if (
            request.episode_id != self.episode_id
            or request.attachment_id != self.attachment_id
            or request.attachment_epoch != self.attachment_epoch
        ):
            return _error(RejectionCategory.STALE_EPOCH, "episode, attachment identity, or epoch is not current")
        try:
            fence = self._fence.snapshot()
        except Exception:
            return _provider_error()
        if not isinstance(fence, CallFence):
            return _provider_error()
        if not fence.open:
            return _error(RejectionCategory.POST_FENCE, "attachment admission is closed")
        if fence.aborted:
            return _error(RejectionCategory.ABORTED, "attachment is cancelled")
        grant = self._grants.current()
        if grant is None or grant.grant_epoch != request.grant_epoch:
            return _error(RejectionCategory.STALE_EPOCH, "grant is not current")
        if self._clock() > min(fence.deadline, grant.deadline):
            return _error(RejectionCategory.DEADLINE, "call deadline has passed")
        return self._precheck_policy(request, grant)

    @staticmethod
    def _precheck_policy(request: ToolRequest, grant: CapabilityGrant) -> ToolError | None:
        if request.method is ToolMethod.WORKSPACE_WRITE:
            if not grant.permits(ToolMethod.WORKSPACE_WRITE):
                return _error(RejectionCategory.WRITE, "no current write grant")
            params = request.params
            if isinstance(params, WriteParams) and not grant.permits_write_path(params.path):
                return _error(RejectionCategory.PATH, "path is not writable under the current grant")
            return None
        if not grant.permits(request.method):
            return _error(RejectionCategory.CAPABILITY, "capability is not granted")
        if request.method is ToolMethod.WORKSPACE_SHELL:
            params = request.params
            if isinstance(params, ShellParams) and params.argv not in grant.allowed_argv:
                return _error(RejectionCategory.ARGV, "argv is not allowed under the current grant")
        return None

    def _execute(self, request: ToolRequest, grant: CapabilityGrant) -> ToolResult:
        with self._state:
            self._adapter_entries += 1
        if request.method is ToolMethod.WORKSPACE_WRITE:
            return self._execute_write(request, grant)
        try:
            data = self._perform(request)
        except Exception:
            return self._finalize(request, error=_provider_error())
        error = self._postcheck(request, grant)
        if error is not None:
            return self._finalize(request, error=error)
        try:
            return self._finalize(request, data=data)
        except TypeError, ValueError:
            return self._finalize(request, error=_provider_error())

    def _perform(self, request: ToolRequest) -> dict[str, object]:
        params = request.params
        if isinstance(params, ReadParams):
            return {"content": self._adapter.read(params.path)}
        if isinstance(params, SearchParams):
            matches = self._adapter.search(params.query, params.path)
            if type(matches) is not tuple or len(matches) > _MAX_SEARCH_RESULTS:
                raise TypeError("adapter search result is not a bounded tuple")
            return {"matches": list(matches)}
        if isinstance(params, ShellParams):
            outcome = self._adapter.shell(params.argv, params.cwd)
            if not isinstance(outcome, ShellOutcome):
                raise TypeError("adapter shell result must be ShellOutcome")
            return {
                "returncode": outcome.returncode,
                "stdout": outcome.stdout,
                "stderr": outcome.stderr,
                "truncated": outcome.truncated,
            }
        test = self._adapter.run_test()
        if not isinstance(test, TestOutcome):
            raise TypeError("adapter test result must be TestOutcome")
        return {"passed": test.passed, "digest": test.evidence_digest}

    def _execute_write(self, request: ToolRequest, grant: CapabilityGrant) -> ToolResult:
        params = request.params
        if not isinstance(params, WriteParams):
            raise AssertionError("write execution requires WriteParams")
        try:
            staged = self._adapter.stage_write(request.call_id, params.path, params.content)
        except Exception:
            return self._finalize(request, error=_provider_error())
        if not isinstance(staged, StagedWrite):
            return self._finalize(request, error=_provider_error())
        with self._state:
            self._stages += 1
        if staged.call_id != request.call_id or staged.path != params.path:
            self._discard(staged)
            return self._finalize(request, error=_provider_error())
        with self._barrier:
            error = self._postcheck(request, grant, write=True)
            if error is not None:
                if not self._discard(staged):
                    error = _provider_error()
                return self._finalize(request, error=error)
            try:
                digest = self._adapter.commit_write(staged)
            except Exception:
                self._discard(staged)
                return self._finalize(request, error=_provider_error())
            with self._state:
                self._commits += 1
                self._target_mutations += 1
            if digest != staged.digest:
                return self._finalize(request, error=_provider_error())
        try:
            return self._finalize(request, data={"committed": True, "digest": digest})
        except TypeError, ValueError:
            return self._finalize(request, error=_provider_error())

    def _postcheck(self, request: ToolRequest, grant: CapabilityGrant, *, write: bool = False) -> ToolError | None:
        """Refresh every fence under the barrier before exactly one commit or admission."""

        with self._barrier:
            try:
                fence = self._fence.snapshot()
            except Exception:
                return _provider_error()
            if not isinstance(fence, CallFence):
                return _provider_error()
            if not fence.open:
                return _error(RejectionCategory.POST_FENCE, "attachment fence closed after staging")
            if fence.aborted:
                return _error(RejectionCategory.ABORTED, "attachment cancelled before commit")
            current = self._grants.current()
            if current is None or current.grant_epoch != grant.grant_epoch:
                return _error(RejectionCategory.STALE_EPOCH, "grant replaced before commit")
            if self._clock() > min(fence.deadline, grant.deadline):
                return _error(RejectionCategory.DEADLINE, "deadline passed before commit")
            if self._admission is not None and not self._admit(request.call_id):
                return _error(RejectionCategory.AUTHORITY, "connection admission rejected the result")
            if write and self._target is not None and not self._target_current():
                return _error(RejectionCategory.POST_FENCE, "target head is no longer current")
        return None

    def _admit(self, call_id: str) -> bool:
        if self._admission is None:
            raise AssertionError("admission seam consulted without being configured")
        try:
            return bool(self._admission.admit(call_id))
        except Exception:
            return False

    def _target_current(self) -> bool:
        if self._target is None:
            raise AssertionError("target seam consulted without being configured")
        try:
            return bool(self._target.is_current())
        except Exception:
            return False

    def cleanup_stages(self) -> int:
        """Remove every outstanding adapter stage as part of attachment settlement."""

        removed = self._adapter.discard_all_stages()
        if type(removed) is not int or removed < 0:
            raise TypeError("adapter discard_all_stages must return a non-negative stage count")
        with self._state:
            self._stage_discards += removed
        return removed

    def _discard(self, staged: StagedWrite) -> bool:
        try:
            self._adapter.discard_write(staged)
        except Exception:
            with self._state:
                self._stage_discard_failures += 1
            return False
        else:
            with self._state:
                self._stage_discards += 1
            return True

    def _reject_unparsed(self, data: object, rejected: ToolRequestRejected) -> ToolResult:
        call_id, episode_id = _salvaged_identity(data)
        error = ToolError(rejected.category, rejected.detail)
        self._record(call_id, episode_id, method=None, ok=False, category=error.category)
        return ToolResult(
            call_id=call_id,
            attachment_id=self.attachment_id,
            epoch=self.attachment_epoch,
            ok=False,
            data=None,
            error=error,
        )

    def _finalize(
        self,
        request: ToolRequest,
        *,
        data: dict[str, object] | None = None,
        error: ToolError | None = None,
    ) -> ToolResult:
        category = None if error is None else error.category
        ok = error is None
        result = ToolResult(
            call_id=request.call_id,
            attachment_id=self.attachment_id,
            epoch=self.attachment_epoch,
            ok=ok,
            data=data,
            error=error,
        )
        self._record(request.call_id, request.episode_id, method=request.method, ok=ok, category=category)
        if ok:
            with self._state:
                self._results_admitted += 1
        return result

    def _record(
        self,
        call_id: str,
        episode_id: str,
        *,
        method: ToolMethod | None,
        ok: bool,
        category: RejectionCategory | None,
    ) -> None:
        with self._state:
            self._sequence += 1
            if category is not None:
                self._rejections[category.value] = self._rejections.get(category.value, 0) + 1
            self._evidence.append(
                CallEvidence(
                    sequence=self._sequence,
                    call_id=call_id,
                    episode_id=episode_id,
                    method=method,
                    ok=ok,
                    category=category,
                    epoch=self.attachment_epoch,
                )
            )


def _error(category: RejectionCategory, detail: str) -> ToolError:
    return ToolError(category, detail)


def _provider_error() -> ToolError:
    return ToolError(RejectionCategory.PROVIDER, "provider operation failed")


def _salvaged_identity(data: object) -> tuple[str, str]:
    call_id, episode_id = _UNPARSED_CALL_ID, _UNPARSED_CALL_ID
    if isinstance(data, dict):
        raw_call, raw_episode = data.get("call_id"), data.get("episode_id")
        if _salvageable(raw_call):
            call_id = raw_call
        if _salvageable(raw_episode):
            episode_id = raw_episode
    return call_id, episode_id


def _salvageable(value: object) -> TypeGuard[str]:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 64
        and value == value.strip()
        and all(ord(character) >= 32 for character in value)
    )


__all__ = [
    "CallEvidence",
    "CallFence",
    "CallFenceSource",
    "GatewayCounters",
    "HandsAdapter",
    "HandsGateway",
    "ResultAdmission",
    "ShellOutcome",
    "StagedWrite",
    "TargetCurrency",
    "TestOutcome",
]
