"""Deterministic executable-world and strict replay contracts.

This module owns scheduling and replay mechanics only. A ``ScenarioProfile``
owns each opaque runtime generation and all application command semantics.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Callable, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

LEGACY_API_COMPATIBILITY = "petrus.testing.dst/v1"
API_COMPATIBILITY = "petrus.testing.dst/v2"
ARTIFACT_FORMAT = "petrus-dst-world"
LEGACY_ARTIFACT_VERSION = 1
ARTIFACT_VERSION = 2
RESULT_FORMAT = "petrus-dst-world-replay-result"
MAX_ARTIFACT_BYTES = 4_194_304

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

type _ActionDisposition = Literal["applied", "idempotent", "refused_expected", "quarantined"]
type _AuthoredDisposition = Literal["converged", "quiescent", "external_wait", "quarantined"]
type _EndingDisposition = Literal[
    "converged", "quiescent", "external_wait", "budget_exhausted", "invariant_failure", "quarantined"
]
type _CommandSource = Literal["authored", "profile"]


class Disposition(StrEnum):
    """Explicit ending classifications for a bounded world run."""

    CONVERGED = "converged"
    QUIESCENT = "quiescent"
    EXTERNAL_WAIT = "external_wait"
    BUDGET_EXHAUSTED = "budget_exhausted"
    INVARIANT_FAILURE = "invariant_failure"
    QUARANTINED = "quarantined"


class ActionDisposition(StrEnum):
    """Outcome of one accepted interpreter command."""

    APPLIED = "applied"
    IDEMPOTENT = "idempotent"
    REFUSED_EXPECTED = "refused_expected"
    QUARANTINED = "quarantined"


class FaultDisposition(StrEnum):
    """Generic fault behavior named by a profile-owned cut."""

    REFUSE = "refuse"
    RAISE = "raise"
    DELAY = "delay"
    DROP = "drop"
    DUPLICATE = "duplicate"


def _strict_json(value: object, subject: str = "value") -> JsonValue:
    """Detach exact JSON data while refusing Python extensions and NaN/Inf."""

    def visit(item: object, path: str) -> JsonValue:
        if item is None or type(item) in (bool, int, str):
            return cast(JsonValue, item)
        if type(item) is float:
            try:
                json.dumps(item, allow_nan=False)
            except ValueError:
                raise ValueError(f"{subject} has a non-finite number at {path}") from None
            return cast(float, item)
        if type(item) is list:
            return [visit(child, f"{path}[{index}]") for index, child in enumerate(cast(list[object], item))]
        if type(item) is dict:
            result: dict[str, JsonValue] = {}
            for key, child in cast(dict[object, object], item).items():
                if type(key) is not str:
                    raise TypeError(f"{subject} has a non-string object key at {path}")
                result[key] = visit(child, f"{path}.{key}")
            return result
        raise TypeError(f"{subject} must be strict JSON data; found {type(item).__name__} at {path}")

    return visit(value, "$")


def digest_json(value: object) -> str:
    """Return the canonical sha256 identity of strict JSON data."""

    detached = _strict_json(value)
    encoded = json.dumps(detached, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ComponentIdentity(_StrictModel):
    """Exact identity and implementation pin for one replay component."""

    name: str
    version: int = Field(ge=1)
    digest: str

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not _NAME.fullmatch(value):
            raise ValueError("component identity name must use letters, digits, '.', ':', '_', or '-'")
        return value

    @field_validator("digest")
    @classmethod
    def valid_digest(cls, value: str) -> str:
        if not _DIGEST.fullmatch(value):
            raise ValueError("component identity digest must be sha256:<64 lowercase hex>")
        return value


class ProfileIdentity(ComponentIdentity):
    """Exact identity of one registered scenario profile."""


class CheckerIdentity(ComponentIdentity):
    """Exact identity of one registered independent checker."""


class Command(_StrictModel):
    """One normalized application command for an exact profile."""

    profile: ProfileIdentity
    name: str
    payload: JsonValue

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not _NAME.fullmatch(value) or value.startswith("dst."):
            raise ValueError("command name must be non-empty, normalized, and outside the reserved 'dst.' namespace")
        return value

    @field_validator("payload", mode="before")
    @classmethod
    def strict_payload(cls, value: object) -> JsonValue:
        return _strict_json(value, "command payload")


class Fault(_StrictModel):
    """One occurrence-addressed fault at a profile-owned semantic cut."""

    profile: ProfileIdentity
    name: str
    target: str
    occurrence: int = Field(ge=1)
    disposition: Literal["refuse", "raise", "delay", "drop", "duplicate"]
    payload: JsonValue

    @field_validator("name", "target")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not _NAME.fullmatch(value):
            raise ValueError("fault name and target must be normalized non-empty names")
        return value

    @field_validator("payload", mode="before")
    @classmethod
    def strict_payload(cls, value: object) -> JsonValue:
        return _strict_json(value, "fault payload")


class Budget(_StrictModel):
    """All generic World limits required by the version-1 test-kit contract."""

    actions: int = Field(ge=1, le=100_000)
    queued_commands: int = Field(ge=1, le=10_000)
    timer_advances: int = Field(ge=0, le=10_000)
    logical_instant: int = Field(ge=0, le=2**53 - 1)
    reloads: int = Field(ge=0, le=1_000)
    predicate_polls: int = Field(ge=1, le=100_000)
    artifact_bytes: int = Field(ge=1, le=MAX_ARTIFACT_BYTES)


class ScheduledCommand(_StrictModel):
    """Detached future work proposed to, but never scheduled by, a profile."""

    instant: int = Field(ge=0, le=2**53 - 1)
    command: Command


class ApplyResult(_StrictModel):
    """Detached result of one profile command."""

    disposition: _ActionDisposition
    value: JsonValue
    scheduled: list[ScheduledCommand]

    @field_validator("value", mode="before")
    @classmethod
    def strict_value(cls, value: object) -> JsonValue:
        return _strict_json(value, "apply result")


@dataclass(frozen=True)
class GenerationStart[GenerationT]:
    """One opaque generation plus work disclosed by create/load."""

    generation: GenerationT
    scheduled: tuple[ScheduledCommand, ...] = ()

    def __post_init__(self) -> None:
        if type(self.scheduled) is not tuple or any(
            not isinstance(command, ScheduledCommand) for command in self.scheduled
        ):
            raise TypeError("GenerationStart.scheduled must be a tuple of ScheduledCommand values")


class ObservationRequest(_StrictModel):
    """A closed profile observation name and strict parameters."""

    name: str
    payload: JsonValue

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not _NAME.fullmatch(value):
            raise ValueError("observation name must be normalized and non-empty")
        return value

    @field_validator("payload", mode="before")
    @classmethod
    def strict_payload(cls, value: object) -> JsonValue:
        return _strict_json(value, "observation payload")


class Observation(_StrictModel):
    """One detached observation at an exact World boundary."""

    name: str
    value: JsonValue
    instant: int = Field(ge=0, le=2**53 - 1)
    generation: int = Field(ge=1)
    sequence: int = Field(ge=0)

    @field_validator("value", mode="before")
    @classmethod
    def strict_value(cls, value: object) -> JsonValue:
        return _strict_json(value, "observation value")


class CheckResult(_StrictModel):
    """Detached verdict returned by one checker invocation."""

    passed: bool
    detail: JsonValue

    @field_validator("detail", mode="before")
    @classmethod
    def strict_detail(cls, value: object) -> JsonValue:
        return _strict_json(value, "checker detail")


class ScenarioProfile[GenerationT](Protocol):
    """Application-owned adapter over one opaque runtime generation."""

    identity: ProfileIdentity

    def validate(self, command: Command) -> Command: ...

    def validate_fault(self, fault: Fault) -> Fault: ...

    def create(self, context: ScenarioContext) -> GenerationStart[GenerationT]: ...

    def load(self, context: ScenarioContext) -> GenerationStart[GenerationT]: ...

    def apply(self, generation: GenerationT, command: Command, context: ScenarioContext) -> ApplyResult: ...

    def observe(self, generation: GenerationT, request: ObservationRequest, context: ScenarioContext) -> JsonValue: ...

    def drop(self, generation: GenerationT) -> None: ...

    def close(self, generation: GenerationT) -> None: ...


class Checker(Protocol):
    """Independent property checked over a detached profile observation."""

    identity: CheckerIdentity
    request: ObservationRequest

    def check(self, observation: Observation) -> CheckResult: ...


class SubmitAttempt(_StrictModel):
    kind: Literal["submit"]
    generation: int = Field(ge=1)
    command: Command


class StepAttempt(_StrictModel):
    kind: Literal["step"]


class FaultAttempt(_StrictModel):
    kind: Literal["activate_fault"]
    generation: int = Field(ge=1)
    fault: Fault


class ObserveAttempt(_StrictModel):
    kind: Literal["observe"]
    generation: int = Field(ge=1)
    request: ObservationRequest
    poll: bool


class CrashAttempt(_StrictModel):
    kind: Literal["crash"]
    generation: int = Field(ge=1)
    cut: str

    @field_validator("cut")
    @classmethod
    def valid_cut(cls, value: str) -> str:
        if not _NAME.fullmatch(value):
            raise ValueError("crash cut must be a normalized non-empty name")
        return value


class RestartAttempt(_StrictModel):
    kind: Literal["restart"]


class FairAttempt(_StrictModel):
    kind: Literal["begin_fair"]
    generation: int = Field(ge=1)


class FinishAttempt(_StrictModel):
    kind: Literal["finish"]
    generation: int = Field(ge=1)
    disposition: _AuthoredDisposition


type OperationAttempt = Annotated[
    SubmitAttempt
    | StepAttempt
    | FaultAttempt
    | ObserveAttempt
    | CrashAttempt
    | RestartAttempt
    | FairAttempt
    | FinishAttempt,
    Field(discriminator="kind"),
]


class BudgetFailure(_StrictModel):
    kind: Literal["budget_exhausted"]
    bound: str
    limit: int = Field(ge=0)
    error: str


class InvariantFailure(_StrictModel):
    kind: Literal["invariant_failure"]
    error: str


type FailureDetail = Annotated[BudgetFailure | InvariantFailure, Field(discriminator="kind")]


class ExecuteOperation(_StrictModel):
    kind: Literal["execute"]
    position: int = Field(ge=0)
    source: _CommandSource
    queue_order: int = Field(ge=0)
    instant: int = Field(ge=0, le=2**53 - 1)
    generation: int = Field(ge=1)
    command: Command
    result: ApplyResult


class FaultOperation(_StrictModel):
    kind: Literal["activate_fault"]
    position: int = Field(ge=0)
    instant: int = Field(ge=0, le=2**53 - 1)
    generation: int = Field(ge=1)
    fault: Fault


class ObserveOperation(_StrictModel):
    kind: Literal["observe"]
    position: int = Field(ge=0)
    poll: bool
    observation: Observation
    request: ObservationRequest


class CrashOperation(_StrictModel):
    kind: Literal["crash"]
    position: int = Field(ge=0)
    instant: int = Field(ge=0, le=2**53 - 1)
    generation: int = Field(ge=1)
    cut: str
    discarded_commands: int = Field(ge=0)

    @field_validator("cut")
    @classmethod
    def valid_cut(cls, value: str) -> str:
        if not _NAME.fullmatch(value):
            raise ValueError("crash cut must be a normalized non-empty name")
        return value


class RestartOperation(_StrictModel):
    kind: Literal["restart"]
    position: int = Field(ge=0)
    instant: int = Field(ge=0, le=2**53 - 1)
    generation: int = Field(ge=1)


class FairOperation(_StrictModel):
    kind: Literal["begin_fair"]
    position: int = Field(ge=0)
    instant: int = Field(ge=0, le=2**53 - 1)
    generation: int = Field(ge=1)


class FinishOperation(_StrictModel):
    kind: Literal["finish"]
    position: int = Field(ge=0)
    instant: int = Field(ge=0, le=2**53 - 1)
    generation: int = Field(ge=1)
    disposition: _AuthoredDisposition


class FailureOperation(_StrictModel):
    kind: Literal["failure"]
    position: int = Field(ge=0)
    instant: int = Field(ge=0, le=2**53 - 1)
    generation: int | None = Field(ge=1)
    accepted_operations: int = Field(ge=0, le=1)
    attempt: OperationAttempt
    failure: FailureDetail


type ExpandedOperationV1 = Annotated[
    ExecuteOperation
    | FaultOperation
    | ObserveOperation
    | CrashOperation
    | RestartOperation
    | FairOperation
    | FinishOperation,
    Field(discriminator="kind"),
]
type ExpandedOperation = Annotated[ExpandedOperationV1 | FailureOperation, Field(discriminator="kind")]


class JournalEntry(_StrictModel):
    """One deterministic diagnostic fact emitted by the interpreter."""

    position: int = Field(ge=0)
    instant: int = Field(ge=0, le=2**53 - 1)
    generation: int | None
    kind: Literal[
        "created",
        "loaded",
        "command",
        "fault",
        "observation",
        "check",
        "crash",
        "fair",
        "finish",
        "budget",
        "failure",
    ]
    name: str
    value: JsonValue

    @field_validator("value", mode="before")
    @classmethod
    def strict_value(cls, value: object) -> JsonValue:
        return _strict_json(value, "journal value")


class ScenarioExpectedV1(_StrictModel):
    disposition: _AuthoredDisposition
    checks: list[JournalEntry]
    journal_digest: str

    @field_validator("journal_digest")
    @classmethod
    def valid_digest(cls, value: str) -> str:
        if not _DIGEST.fullmatch(value):
            raise ValueError("journal digest must be sha256:<64 lowercase hex>")
        return value


class ScenarioArtifactV1(_StrictModel):
    """Legacy strict expanded operations and exact expected authored outcome."""

    format: Literal["petrus-dst-world"]
    version: Literal[1]
    api: Literal["petrus.testing.dst/v1"]
    scenario_id: str
    profile: ProfileIdentity
    checkers: list[CheckerIdentity]
    budget: Budget
    operations: list[ExpandedOperationV1]
    expected: ScenarioExpectedV1

    @field_validator("scenario_id")
    @classmethod
    def valid_scenario_id(cls, value: str) -> str:
        if not _NAME.fullmatch(value):
            raise ValueError("scenario id must be a normalized non-empty name")
        return value

    @model_validator(mode="after")
    def coherent(self) -> ScenarioArtifactV1:
        if [operation.position for operation in self.operations] != list(range(len(self.operations))):
            raise ValueError("DST operation positions must be dense and zero-based")
        check_positions = [entry.position for entry in self.expected.checks]
        if check_positions != sorted(set(check_positions)) or any(
            entry.kind != "check" for entry in self.expected.checks
        ):
            raise ValueError("DST expected checks must be ordered unique check-journal entries")
        identities = [_identity_key(identity) for identity in self.checkers]
        if len(identities) != len(set(identities)):
            raise ValueError("DST checker manifest identities must be unique")
        for operation in self.operations:
            if isinstance(operation, ExecuteOperation) and operation.command.profile != self.profile:
                raise ValueError("DST operation command does not match the artifact profile")
            if isinstance(operation, FaultOperation) and operation.fault.profile != self.profile:
                raise ValueError("DST operation fault does not match the artifact profile")
        return self


class ScenarioExpected(_StrictModel):
    disposition: _EndingDisposition
    failure: FailureDetail | None
    checks: list[JournalEntry]
    journal_digest: str

    @field_validator("journal_digest")
    @classmethod
    def valid_digest(cls, value: str) -> str:
        if not _DIGEST.fullmatch(value):
            raise ValueError("journal digest must be sha256:<64 lowercase hex>")
        return value


class ScenarioArtifact(_StrictModel):
    """Strict version-2 operations including an exact terminal failure attempt."""

    format: Literal["petrus-dst-world"]
    version: Literal[2]
    api: Literal["petrus.testing.dst/v2"]
    scenario_id: str
    profile: ProfileIdentity
    checkers: list[CheckerIdentity]
    budget: Budget
    operations: list[ExpandedOperation]
    expected: ScenarioExpected

    @field_validator("scenario_id")
    @classmethod
    def valid_scenario_id(cls, value: str) -> str:
        if not _NAME.fullmatch(value):
            raise ValueError("scenario id must be a normalized non-empty name")
        return value

    @model_validator(mode="after")
    def coherent(self) -> ScenarioArtifact:
        self._validate_shape()
        self._validate_failure()
        self._validate_profiles()
        return self

    def _validate_shape(self) -> None:
        if [operation.position for operation in self.operations] != list(range(len(self.operations))):
            raise ValueError("DST operation positions must be dense and zero-based")
        check_positions = [entry.position for entry in self.expected.checks]
        if check_positions != sorted(set(check_positions)) or any(
            entry.kind != "check" for entry in self.expected.checks
        ):
            raise ValueError("DST expected checks must be ordered unique check-journal entries")
        identities = [_identity_key(identity) for identity in self.checkers]
        if len(identities) != len(set(identities)):
            raise ValueError("DST checker manifest identities must be unique")

    def _validate_failure(self) -> None:
        failures = [operation for operation in self.operations if isinstance(operation, FailureOperation)]
        expected_failure = self.expected.disposition in {"budget_exhausted", "invariant_failure"}
        if expected_failure:
            if len(failures) != 1 or not self.operations or self.operations[-1] != failures[0]:
                raise ValueError("a failed DST artifact must end with exactly one failure operation")
            if failures[0].failure != self.expected.failure:
                raise ValueError("DST expected failure must equal the terminal failure operation")
            if failures[0].accepted_operations:
                if len(self.operations) < 2 or not _attempt_produced_operation(
                    failures[0].attempt, self.operations[-2]
                ):
                    raise ValueError("DST failed attempt does not identify its accepted operation")
        elif failures or self.expected.failure is not None:
            raise ValueError("a successful DST artifact cannot contain an expected failure")

    def _validate_profiles(self) -> None:
        for operation in self.operations:
            if isinstance(operation, ExecuteOperation) and operation.command.profile != self.profile:
                raise ValueError("DST operation command does not match the artifact profile")
            if isinstance(operation, FaultOperation) and operation.fault.profile != self.profile:
                raise ValueError("DST operation fault does not match the artifact profile")
            if isinstance(operation, FailureOperation):
                if operation.failure.kind != self.expected.disposition:
                    raise ValueError("DST terminal failure kind must equal the expected disposition")
                attempt = operation.attempt
                if isinstance(attempt, SubmitAttempt) and attempt.command.profile != self.profile:
                    raise ValueError("DST failed command attempt does not match the artifact profile")
                if isinstance(attempt, FaultAttempt) and attempt.fault.profile != self.profile:
                    raise ValueError("DST failed fault attempt does not match the artifact profile")


class ReplayResultV1(_StrictModel):
    format: Literal["petrus-dst-world-replay-result"]
    version: Literal[1]
    scenario_id: str
    outcome: Literal["pass"]
    disposition: _AuthoredDisposition
    operations: int = Field(ge=0)
    journal_entries: int = Field(ge=0)
    journal_digest: str


class ReplayResult(_StrictModel):
    format: Literal["petrus-dst-world-replay-result"]
    version: Literal[2]
    scenario_id: str
    outcome: Literal["pass"]
    disposition: _EndingDisposition
    failure: FailureDetail | None
    operations: int = Field(ge=0)
    journal_entries: int = Field(ge=0)
    journal_digest: str


class DstError(RuntimeError):
    """Base error for deterministic World contract failures."""


class StaleGeneration(DstError):
    """A Timeline attempted to use a revoked runtime generation."""


class PendingWork(DstError):
    """An authored command attempted to overtake eligible scheduled work."""


class BudgetExhausted(DstError):
    """A World reached one explicit budget before the requested operation."""

    def __init__(self, bound: str, limit: int):
        self.bound = bound
        self.limit = limit
        super().__init__(f"DST budget {bound!r} exhausted at limit {limit}")


class InvariantViolation(AssertionError):
    """An independent checker refused an atomic World boundary."""


class ReplayMismatch(AssertionError):
    """Expanded replay diverged from its strict artifact."""


class RunUntilFailed(AssertionError):
    """A named debugger checkpoint could not be reached within its World."""

    def __init__(
        self,
        name: str,
        disposition: Disposition,
        observation: Observation,
        pending: list[JsonValue],
        journal: tuple[JournalEntry, ...],
        budget: Budget,
    ):
        self.name = name
        self.disposition = disposition
        self.observation = observation
        self.pending = pending
        self.journal = journal
        self.budget = budget
        super().__init__(
            f"DST run_until {name!r} ended as {disposition.value}; "
            f"last={observation.model_dump(mode='json')!r}; pending={pending!r}; "
            f"journal_tail={[entry.model_dump(mode='json') for entry in journal[-8:]]!r}"
        )


@dataclass(order=True)
class _Queued:
    instant: int
    order: int
    generation: int
    source: _CommandSource
    command: Command


@dataclass
class _ActiveFault:
    fault: Fault
    seen: int = 0


class ScenarioContext:
    """Deterministic services available only while a profile operation runs."""

    __slots__ = ("__world",)

    def __init__(self, world: World):
        self.__world = world

    def now(self) -> int:
        return self.__world.instant

    def stable_id(self, namespace: str) -> str:
        if not _NAME.fullmatch(namespace):
            raise ValueError("stable id namespace must be a normalized non-empty name")
        return self.__world._stable_id(namespace)

    def faults(self, target: str) -> tuple[Fault, ...]:
        if not _NAME.fullmatch(target):
            raise ValueError("fault target must be a normalized non-empty name")
        return self.__world._faults(target)


class ScenarioRegistry:
    """Explicit fail-closed registry for replay profiles and checkers."""

    def __init__(self) -> None:
        self._profiles: dict[tuple[str, int, str], ScenarioProfile[object]] = {}
        self._checkers: dict[tuple[str, int, str], Checker] = {}

    def register_profile[GenerationT](self, profile: ScenarioProfile[GenerationT]) -> None:
        key = _identity_key(profile.identity)
        if key in self._profiles:
            raise ValueError(f"DST profile identity is already registered: {profile.identity}")
        self._profiles[key] = cast(ScenarioProfile[object], profile)

    def register_checker(self, checker: Checker) -> None:
        key = _identity_key(checker.identity)
        if key in self._checkers:
            raise ValueError(f"DST checker identity is already registered: {checker.identity}")
        self._checkers[key] = checker

    def profile(self, identity: ProfileIdentity) -> ScenarioProfile[object]:
        try:
            return self._profiles[_identity_key(identity)]
        except KeyError:
            raise ValueError(f"DST artifact profile is not registered exactly: {identity}") from None

    def checkers(self, manifest: list[CheckerIdentity]) -> tuple[Checker, ...]:
        resolved = []
        for identity in manifest:
            try:
                resolved.append(self._checkers[_identity_key(identity)])
            except KeyError:
                raise ValueError(f"DST artifact checker is not registered exactly: {identity}") from None
        return tuple(resolved)


class World:
    """One deterministic interpreter over an application-owned runtime profile."""

    def __init__(self, profile: ScenarioProfile[object], budget: Budget, *, checkers: tuple[Checker, ...] = ()):
        self.profile = profile
        self.budget = budget
        self.checkers = checkers
        checker_keys = [_identity_key(checker.identity) for checker in checkers]
        if len(checker_keys) != len(set(checker_keys)):
            raise ValueError("DST World checker identities must be unique")
        self.instant = 0
        self._context = ScenarioContext(self)
        self._generation: object | None = None
        self._generation_id: int | None = None
        self._last_generation_id = 0
        self._queue: list[_Queued] = []
        self._queue_order = 0
        self._operations: list[ExpandedOperation] = []
        self._journal: list[JournalEntry] = []
        self._active_faults: list[_ActiveFault] = []
        self._ids: dict[str, int] = {}
        self._inside_profile = False
        self._actions = 0
        self._timer_advances = 0
        self._reloads = 0
        self._predicate_polls = 0
        self._fair = False
        self._disposition: Disposition | None = None
        try:
            started = self._invoke(self.profile.create, self._context)
            self._install_generation(started, loaded=False)
        except BaseException:
            if self._generation is not None:
                generation = self._generation
                self._generation = None
                self._generation_id = None
                self._queue.clear()
                self._invoke(self.profile.close, generation)
            raise

    @property
    def generation(self) -> int | None:
        return self._generation_id

    @property
    def operations(self) -> tuple[ExpandedOperation, ...]:
        return tuple(self._operations)

    @property
    def journal(self) -> tuple[JournalEntry, ...]:
        return tuple(self._journal)

    @property
    def disposition(self) -> Disposition | None:
        return self._disposition

    def timeline(self) -> Timeline:
        if self._generation_id is None:
            raise StaleGeneration("DST World has no live generation; restart before creating a Timeline")
        return Timeline(self, self._generation_id)

    def submit(self, command: Command, *, generation: int) -> ApplyResult:
        attempt = SubmitAttempt(kind="submit", generation=generation, command=command)
        return self._attempt(attempt, lambda: self._submit(command, generation=generation))

    def _submit(self, command: Command, *, generation: int) -> ApplyResult:
        self._require_generation(generation)
        if self._fair:
            raise DstError("authored commands cannot enter an active DST fair phase")
        if self._queue and self._queue[0].instant <= self.instant:
            raise PendingWork("run eligible profile work before submitting another authored command")
        order = self._enqueue(ScheduledCommand(instant=self.instant, command=command), "authored")
        executed = self._step()
        if executed.queue_order != order:
            raise AssertionError("DST authored command was not the scheduler's next total-order choice")
        return executed.result

    def step(self) -> ExecuteOperation:
        return self._attempt(StepAttempt(kind="step"), self._step)

    def _step(self) -> ExecuteOperation:
        self._require_unfinished()
        if self._generation_id is None or self._generation is None:
            raise StaleGeneration("DST World has no live generation")
        if not self._queue:
            raise DstError("DST World is waiting with no scheduled command")
        queued = self._queue[0]
        if queued.generation != self._generation_id:
            raise StaleGeneration(f"queued generation {queued.generation} is no longer live")
        if queued.instant > self.instant:
            if self._timer_advances >= self.budget.timer_advances:
                self._exhaust("timer_advances", self.budget.timer_advances)
            if queued.instant > self.budget.logical_instant:
                self._exhaust("logical_instant", self.budget.logical_instant)
        self._reserve_action()
        heapq.heappop(self._queue)
        if queued.instant > self.instant:
            self._timer_advances += 1
            self.instant = queued.instant
        validated = queued.command
        result = self._invoke(self.profile.apply, self._generation, validated, self._context)
        if not isinstance(result, ApplyResult):
            raise TypeError("ScenarioProfile.apply must return ApplyResult")
        position = len(self._operations)
        operation = ExecuteOperation(
            kind="execute",
            position=position,
            source=queued.source,
            queue_order=queued.order,
            instant=self.instant,
            generation=self._generation_id,
            command=validated,
            result=result,
        )
        self._operations.append(operation)
        self._record("command", validated.name, operation.model_dump(mode="json"))
        self._enqueue_all(result.scheduled, "profile")
        self._evaluate_checkers(validated.name, position, self._generation, self._generation_id)
        return operation

    def activate_fault(self, fault: Fault, *, generation: int) -> None:
        attempt = FaultAttempt(kind="activate_fault", generation=generation, fault=fault)
        self._attempt(attempt, lambda: self._activate_fault(fault, generation=generation))

    def _activate_fault(self, fault: Fault, *, generation: int) -> None:
        self._require_generation(generation)
        self._require_unfinished()
        if self._fair:
            raise DstError("faults cannot enter an active DST fair phase")
        if fault.profile != self.profile.identity:
            raise ValueError("DST fault profile does not match this World")
        if self._queue and self._queue[0].instant <= self.instant:
            raise PendingWork("a fault cannot overtake already eligible profile work")
        validated = self.profile.validate_fault(fault)
        if not isinstance(validated, Fault) or validated.profile != self.profile.identity:
            raise TypeError("ScenarioProfile.validate_fault must return a Fault for its exact identity")
        self._reserve_action()
        position = len(self._operations)
        operation = FaultOperation(
            kind="activate_fault",
            position=position,
            instant=self.instant,
            generation=generation,
            fault=validated,
        )
        self._operations.append(operation)
        self._active_faults.append(_ActiveFault(validated))
        self._record("fault", validated.name, operation.model_dump(mode="json"))
        live, _ = self._live_generation()
        self._evaluate_checkers(f"fault:{validated.name}", position, live, generation)

    def observe(self, request: ObservationRequest, *, generation: int, poll: bool = False) -> Observation:
        attempt = ObserveAttempt(kind="observe", generation=generation, request=request, poll=poll)
        return self._attempt(attempt, lambda: self._observe(request, generation=generation, poll=poll))

    def _observe(self, request: ObservationRequest, *, generation: int, poll: bool) -> Observation:
        self._require_generation(generation)
        self._require_unfinished()
        self._reserve_action()
        if poll:
            if self._predicate_polls >= self.budget.predicate_polls:
                self._exhaust("predicate_polls", self.budget.predicate_polls)
            self._predicate_polls += 1
        position = len(self._operations)
        observation = self._observe_without_journal(request, position)
        operation = ObserveOperation(
            kind="observe", position=position, poll=poll, observation=observation, request=request
        )
        self._operations.append(operation)
        self._record("observation", request.name, operation.model_dump(mode="json"))
        return observation

    def crash(self, cut: str, *, generation: int) -> None:
        attempt = CrashAttempt(kind="crash", generation=generation, cut=cut)
        self._attempt(attempt, lambda: self._crash(cut, generation=generation))

    def _crash(self, cut: str, *, generation: int) -> None:
        self._require_generation(generation)
        self._require_unfinished()
        if self._fair:
            raise DstError("process crashes cannot enter an active DST fair phase")
        if not _NAME.fullmatch(cut):
            raise ValueError("crash cut must be a normalized non-empty name")
        self._reserve_action()
        dropped, dropped_id = self._live_generation()
        position = len(self._operations)
        captured = self._capture_checks(f"crash:{cut}", position, dropped, dropped_id)
        discarded = len(self._queue)
        self._generation = None
        self._generation_id = None
        self._queue.clear()
        self._invoke(self.profile.drop, dropped)
        operation = CrashOperation(
            kind="crash",
            position=position,
            instant=self.instant,
            generation=dropped_id,
            cut=cut,
            discarded_commands=discarded,
        )
        self._operations.append(operation)
        self._record("crash", cut, operation.model_dump(mode="json"), generation=None)
        self._record_checks(captured)

    def restart(self) -> int:
        return self._attempt(RestartAttempt(kind="restart"), self._restart)

    def _restart(self) -> int:
        self._require_unfinished()
        if self._generation is not None or self._generation_id is not None:
            raise DstError("DST restart requires an abruptly dropped generation")
        if self._reloads >= self.budget.reloads:
            self._exhaust("reloads", self.budget.reloads)
        self._reserve_action()
        self._reloads += 1
        started = self._invoke(self.profile.load, self._context)
        self._install_generation(started, loaded=True)
        live, generation_id = self._live_generation()
        position = len(self._operations)
        operation = RestartOperation(kind="restart", position=position, instant=self.instant, generation=generation_id)
        self._operations.append(operation)
        self._record("loaded", self.profile.identity.name, operation.model_dump(mode="json"))
        self._evaluate_checkers("load", position, live, generation_id)
        return generation_id

    def begin_fair(self, *, generation: int) -> None:
        attempt = FairAttempt(kind="begin_fair", generation=generation)
        self._attempt(attempt, lambda: self._begin_fair(generation=generation))

    def _begin_fair(self, *, generation: int) -> None:
        self._require_generation(generation)
        self._require_unfinished()
        if self._fair:
            raise DstError("DST fair phase has already begun")
        if self._active_faults:
            raise DstError("DST fair phase requires every activated fault to be consumed")
        self._reserve_action()
        self._fair = True
        position = len(self._operations)
        operation = FairOperation(kind="begin_fair", position=position, instant=self.instant, generation=generation)
        self._operations.append(operation)
        self._record("fair", "begin", operation.model_dump(mode="json"))
        live, _ = self._live_generation()
        self._evaluate_checkers("begin_fair", position, live, generation)

    def finish(self, disposition: Disposition, *, generation: int) -> None:
        if disposition not in {
            Disposition.CONVERGED,
            Disposition.QUIESCENT,
            Disposition.EXTERNAL_WAIT,
            Disposition.QUARANTINED,
        }:
            raise ValueError(f"DST disposition {disposition.value!r} is reserved for interpreter failures")
        attempt = FinishAttempt(kind="finish", generation=generation, disposition=disposition.value)
        self._attempt(attempt, lambda: self._finish(disposition, generation=generation))

    def _finish(self, disposition: Disposition, *, generation: int) -> None:
        self._require_generation(generation)
        self._require_unfinished()
        if self._fair and disposition is Disposition.EXTERNAL_WAIT:
            raise DstError("an active DST fair phase cannot end as an external wait")
        if self._queue:
            raise PendingWork(f"cannot finish {disposition.value} while scheduled work remains")
        self._reserve_action()
        position = len(self._operations)
        operation = FinishOperation(
            kind="finish",
            position=position,
            instant=self.instant,
            generation=generation,
            disposition=cast(_AuthoredDisposition, disposition.value),
        )
        self._operations.append(operation)
        self._disposition = disposition
        self._record("finish", disposition.value, operation.model_dump(mode="json"))

    def artifact(self, scenario_id: str) -> ScenarioArtifact:
        if self._disposition is None:
            raise DstError("finish the DST World before producing an artifact")
        failures = [operation for operation in self._operations if isinstance(operation, FailureOperation)]
        failure = failures[-1].failure if failures else None
        artifact = ScenarioArtifact(
            format=ARTIFACT_FORMAT,
            version=ARTIFACT_VERSION,
            api=API_COMPATIBILITY,
            scenario_id=scenario_id,
            profile=self.profile.identity,
            checkers=[checker.identity for checker in self.checkers],
            budget=self.budget,
            operations=list(self._operations),
            expected=ScenarioExpected(
                disposition=self._disposition.value,
                failure=failure,
                checks=[entry for entry in self._journal if entry.kind == "check"],
                journal_digest=_journal_digest(self._journal),
            ),
        )
        encode_artifact(artifact)
        return artifact

    def close(self) -> None:
        if self._generation is None:
            return
        generation = self._generation
        self._generation = None
        self._generation_id = None
        self._queue.clear()
        self._invoke(self.profile.close, generation)

    def pending(self) -> list[JsonValue]:
        return [
            _strict_json(
                {
                    "instant": item.instant,
                    "order": item.order,
                    "generation": item.generation,
                    "source": item.source,
                    "command": item.command.model_dump(mode="json"),
                }
            )
            for item in sorted(self._queue)
        ]

    def _install_generation(self, started: object, *, loaded: bool) -> None:
        if not isinstance(started, GenerationStart):
            door = "load" if loaded else "create"
            raise TypeError(f"ScenarioProfile.{door} must return GenerationStart")
        self._last_generation_id += 1
        self._generation_id = self._last_generation_id
        self._generation = started.generation
        self._enqueue_all(started.scheduled, "profile")
        if not loaded:
            self._record(
                "created",
                self.profile.identity.name,
                {"scheduled": [entry.model_dump(mode="json") for entry in started.scheduled]},
            )
            self._evaluate_checkers("create", 0, self._generation, self._generation_id)

    def _enqueue(self, scheduled: ScheduledCommand, source: _CommandSource) -> int:
        if self._generation_id is None:
            raise StaleGeneration("cannot schedule work without a live generation")
        if scheduled.instant < self.instant:
            raise ValueError("DST profile cannot schedule a command in the past")
        if scheduled.instant > self.budget.logical_instant:
            self._exhaust("logical_instant", self.budget.logical_instant)
        command = self._validate(scheduled.command)
        if len(self._queue) >= self.budget.queued_commands:
            self._exhaust("queued_commands", self.budget.queued_commands)
        return self._enqueue_validated(scheduled.instant, command, source)

    def _enqueue_validated(self, instant: int, command: Command, source: _CommandSource) -> int:
        _, generation_id = self._live_generation()
        order = self._queue_order
        self._queue_order += 1
        heapq.heappush(self._queue, _Queued(instant, order, generation_id, source, command))
        return order

    def _enqueue_all(
        self, scheduled_commands: list[ScheduledCommand] | tuple[ScheduledCommand, ...], source: _CommandSource
    ) -> None:
        if len(self._queue) + len(scheduled_commands) > self.budget.queued_commands:
            self._exhaust("queued_commands", self.budget.queued_commands)
        validated = []
        for scheduled in scheduled_commands:
            if not isinstance(scheduled, ScheduledCommand):
                raise TypeError("profile follow-up work must contain only ScheduledCommand values")
            if scheduled.instant < self.instant:
                raise ValueError("DST profile cannot schedule a command in the past")
            if scheduled.instant > self.budget.logical_instant:
                self._exhaust("logical_instant", self.budget.logical_instant)
            validated.append((scheduled.instant, self._validate(scheduled.command)))
        for instant, command in validated:
            self._enqueue_validated(instant, command, source)

    def _validate(self, command: Command) -> Command:
        if command.profile != self.profile.identity:
            raise ValueError("DST command profile does not match this World")
        validated = self.profile.validate(command)
        if not isinstance(validated, Command) or validated.profile != self.profile.identity:
            raise TypeError("ScenarioProfile.validate must return a Command for its exact identity")
        return validated

    def _observe_without_journal(self, request: ObservationRequest, sequence: int) -> Observation:
        if self._generation is None or self._generation_id is None:
            raise StaleGeneration("cannot observe without a live generation")
        value = self._invoke(self.profile.observe, self._generation, request, self._context)
        return Observation(
            name=request.name,
            value=_strict_json(value, "profile observation"),
            instant=self.instant,
            generation=self._generation_id,
            sequence=sequence,
        )

    def _capture_checks(
        self, trigger: str, sequence: int, generation: object, generation_id: int
    ) -> list[tuple[Checker, Observation, CheckResult, str]]:
        captured = []
        for checker in self.checkers:
            value = self._invoke(self.profile.observe, generation, checker.request, self._context)
            observation = Observation(
                name=checker.request.name,
                value=_strict_json(value, "checker observation"),
                instant=self.instant,
                generation=generation_id,
                sequence=sequence,
            )
            result = checker.check(observation)
            if not isinstance(result, CheckResult):
                raise TypeError("Checker.check must return CheckResult")
            captured.append((checker, observation, result, trigger))
        return captured

    def _record_checks(self, captured: list[tuple[Checker, Observation, CheckResult, str]]) -> None:
        failed = []
        for checker, observation, result, trigger in captured:
            self._record(
                "check",
                checker.identity.name,
                {
                    "checker": checker.identity.model_dump(mode="json"),
                    "trigger": trigger,
                    "observation": observation.model_dump(mode="json"),
                    "result": result.model_dump(mode="json"),
                },
                generation=observation.generation,
            )
            if not result.passed:
                failed.append(checker.identity.name)
        if failed:
            self._disposition = Disposition.INVARIANT_FAILURE
            raise InvariantViolation(f"DST checker failure after atomic boundary: {failed}")

    def _evaluate_checkers(self, trigger: str, sequence: int, generation: object, generation_id: int) -> None:
        self._record_checks(self._capture_checks(trigger, sequence, generation, generation_id))

    def _record(self, kind: str, name: str, value: object, *, generation: int | None | object = ...) -> None:
        actual_generation = self._generation_id if generation is ... else cast(int | None, generation)
        self._journal.append(
            JournalEntry(
                position=len(self._journal),
                instant=self.instant,
                generation=actual_generation,
                kind=cast(
                    Literal[
                        "created",
                        "loaded",
                        "command",
                        "fault",
                        "observation",
                        "check",
                        "crash",
                        "fair",
                        "finish",
                        "budget",
                        "failure",
                    ],
                    kind,
                ),
                name=name,
                value=_strict_json(value, "journal value"),
            )
        )

    def _reserve_action(self) -> None:
        if self._actions >= self.budget.actions:
            self._exhaust("actions", self.budget.actions)
        self._actions += 1

    def _exhaust(self, bound: str, limit: int) -> None:
        self._disposition = Disposition.BUDGET_EXHAUSTED
        self._record("budget", bound, {"limit": limit})
        raise BudgetExhausted(bound, limit)

    def _attempt[ResultT](self, attempt: OperationAttempt, operation: Callable[[], ResultT]) -> ResultT:
        before = len(self._operations)
        try:
            return operation()
        except (BudgetExhausted, InvariantViolation) as error:
            if isinstance(error, BudgetExhausted):
                if self._disposition is not Disposition.BUDGET_EXHAUSTED:
                    raise
                failure: FailureDetail = BudgetFailure(
                    kind="budget_exhausted",
                    bound=error.bound,
                    limit=error.limit,
                    error=str(error),
                )
            else:
                if self._disposition is not Disposition.INVARIANT_FAILURE:
                    raise
                failure = InvariantFailure(kind="invariant_failure", error=str(error))
            accepted_operations = len(self._operations) - before
            if accepted_operations not in {0, 1}:
                raise AssertionError("one DST interpreter attempt accepted more than one operation")
            failure_operation = FailureOperation(
                kind="failure",
                position=len(self._operations),
                instant=self.instant,
                generation=self._generation_id,
                accepted_operations=accepted_operations,
                attempt=attempt,
                failure=failure,
            )
            self._operations.append(failure_operation)
            self._record("failure", failure.kind, failure_operation.model_dump(mode="json"))
            raise

    def _stable_id(self, namespace: str) -> str:
        if not self._inside_profile:
            raise DstError("ScenarioContext.stable_id is available only during a profile operation")
        value = self._ids.get(namespace, 0) + 1
        self._ids[namespace] = value
        return f"{namespace}-{value:08d}"

    def _faults(self, target: str) -> tuple[Fault, ...]:
        if not self._inside_profile:
            raise DstError("ScenarioContext.faults is available only during a profile operation")
        matched = []
        retained = []
        for active in self._active_faults:
            if active.fault.target == target:
                active.seen += 1
                if active.seen == active.fault.occurrence:
                    matched.append(active.fault)
                    continue
            retained.append(active)
        self._active_faults = retained
        return tuple(matched)

    def _invoke(self, operation, *arguments):
        if self._inside_profile:
            raise DstError("ScenarioProfile cannot recursively enter the World interpreter")
        self._inside_profile = True
        try:
            return operation(*arguments)
        finally:
            self._inside_profile = False

    def _require_generation(self, generation: int) -> None:
        if self._generation_id != generation:
            raise StaleGeneration(f"DST generation {generation} is stale; live generation is {self._generation_id}")

    def _live_generation(self) -> tuple[object, int]:
        if self._generation is None or self._generation_id is None:
            raise StaleGeneration("DST World has no live generation")
        return self._generation, self._generation_id

    def _require_unfinished(self) -> None:
        if self._disposition is not None:
            raise DstError(f"DST World already ended as {self._disposition.value}")


class Timeline:
    """Imperative authoring facade bound to one revocable World generation."""

    def __init__(self, world: World, generation: int):
        self._world = world
        self.generation = generation

    def command(self, name: str, payload: object) -> ApplyResult:
        return self._world.submit(
            Command(profile=self._world.profile.identity, name=name, payload=_strict_json(payload)),
            generation=self.generation,
        )

    def activate_fault(
        self,
        name: str,
        target: str,
        *,
        occurrence: int = 1,
        disposition: FaultDisposition = FaultDisposition.RAISE,
        payload: object = None,
    ) -> None:
        self._world.activate_fault(
            Fault(
                profile=self._world.profile.identity,
                name=name,
                target=target,
                occurrence=occurrence,
                disposition=disposition.value,
                payload=_strict_json(payload),
            ),
            generation=self.generation,
        )

    def observe(self, name: str, payload: object = None) -> Observation:
        return self._world.observe(
            ObservationRequest(name=name, payload=_strict_json(payload)), generation=self.generation
        )

    def run_until(self, name: str, predicate, *, payload: object = None) -> Observation:
        request = ObservationRequest(name=name, payload=_strict_json(payload))
        while True:
            observation = self._world.observe(request, generation=self.generation, poll=True)
            if predicate(observation):
                return observation
            if not self._world._queue:
                raise RunUntilFailed(
                    name,
                    Disposition.EXTERNAL_WAIT,
                    observation,
                    self._world.pending(),
                    self._world.journal,
                    self._world.budget,
                )
            self._world.step()

    def crash(self, cut: str) -> None:
        self._world.crash(cut, generation=self.generation)

    def begin_fair(self) -> None:
        self._world.begin_fair(generation=self.generation)

    def finish(self, disposition: Disposition) -> None:
        self._world.finish(disposition, generation=self.generation)


type AnyScenarioArtifact = ScenarioArtifactV1 | ScenarioArtifact


def encode_artifact(artifact: AnyScenarioArtifact) -> bytes:
    """Encode one canonical strict artifact and enforce its byte budget."""

    payload = json.dumps(
        artifact.model_dump(mode="json"), allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode()
    if len(payload) > artifact.budget.artifact_bytes:
        raise ValueError(f"DST artifact has {len(payload)} bytes; limit is {artifact.budget.artifact_bytes}")
    return payload


def decode_artifact(payload: bytes) -> AnyScenarioArtifact:
    """Decode strict JSON with duplicate-key, finite-number, and size refusal."""

    if len(payload) > MAX_ARTIFACT_BYTES:
        raise ValueError(f"DST artifact exceeds the format ceiling of {MAX_ARTIFACT_BYTES} bytes")
    try:
        value = json.loads(payload, object_pairs_hook=_strict_object, parse_constant=_refuse_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid strict DST JSON: {error}") from None
    if type(value) is not dict:
        raise ValueError("invalid strict DST JSON: artifact must be an object")
    version = value.get("version")
    if version == LEGACY_ARTIFACT_VERSION:
        artifact: AnyScenarioArtifact = ScenarioArtifactV1.model_validate(value, strict=True)
    elif version == ARTIFACT_VERSION:
        artifact = ScenarioArtifact.model_validate(value, strict=True)
    else:
        raise ValueError(f"unsupported DST artifact version {version!r}")
    if len(payload) > artifact.budget.artifact_bytes:
        raise ValueError(f"DST artifact has {len(payload)} bytes; limit is {artifact.budget.artifact_bytes}")
    return artifact


def load_artifact(path: Path) -> AnyScenarioArtifact:
    """Load one strict artifact from an explicit path."""

    return decode_artifact(path.read_bytes())


type AnyReplayResult = ReplayResultV1 | ReplayResult


def replay(artifact: AnyScenarioArtifact, registry: ScenarioRegistry) -> AnyReplayResult:
    """Replay expanded operations through the same World interpreter."""

    profile = registry.profile(artifact.profile)
    checkers = registry.checkers(artifact.checkers)
    world = World(profile, artifact.budget, checkers=checkers)
    try:
        _replay_operations(world, artifact)
        if world.disposition is None:
            raise ReplayMismatch("DST replay ended without an explicit disposition")
        if world.disposition.value != artifact.expected.disposition:
            raise ReplayMismatch(
                f"DST disposition diverged: expected {artifact.expected.disposition!r}, "
                f"observed {world.disposition.value!r}"
            )
        actual_checks = [entry for entry in world.journal if entry.kind == "check"]
        if actual_checks != artifact.expected.checks:
            raise ReplayMismatch("DST replay checker results diverged from the expanded artifact")
        digest = _journal_digest(world.journal)
        if digest != artifact.expected.journal_digest:
            raise ReplayMismatch("DST replay journal digest diverged")
        result = {
            "format": RESULT_FORMAT,
            "version": artifact.version,
            "scenario_id": artifact.scenario_id,
            "outcome": "pass",
            "disposition": world.disposition.value,
            "operations": len(world.operations),
            "journal_entries": len(world.journal),
            "journal_digest": digest,
        }
        if isinstance(artifact, ScenarioArtifactV1):
            return ReplayResultV1.model_validate(result, strict=True)
        result["failure"] = artifact.expected.failure
        return ReplayResult.model_validate(result, strict=True)
    finally:
        world.close()


def _replay_operations(world: World, artifact: AnyScenarioArtifact) -> None:
    position = 0
    while position < len(artifact.operations):
        expected = artifact.operations[position]
        following = artifact.operations[position + 1] if position + 1 < len(artifact.operations) else None
        paired_failure = (
            following if isinstance(following, FailureOperation) and following.accepted_operations == 1 else None
        )
        before = len(world.operations)
        failed = False
        try:
            _replay_operation(world, expected)
        except BudgetExhausted, InvariantViolation:
            failed = True
        actual = world.operations[before:]
        expected_actual = tuple(artifact.operations[before : before + len(actual)])
        if not actual or actual != expected_actual:
            raise ReplayMismatch(
                f"DST operation {expected.position} diverged: expected {expected_actual!r}, observed {actual!r}"
            )
        position += len(actual)
        if failed:
            if not isinstance(actual[-1], FailureOperation) or position != len(artifact.operations):
                raise ReplayMismatch("DST replay failed outside its exact terminal failure operation")
            return
        if paired_failure is not None:
            raise ReplayMismatch(f"DST operation {expected.position} did not reproduce its terminal failed attempt")
        if len(actual) != 1 or isinstance(expected, FailureOperation):
            raise ReplayMismatch(f"DST expected failure operation {expected.position} did not fail")


def _replay_operation(world: World, expected: ExpandedOperation) -> None:
    match expected:
        case ExecuteOperation(source="authored", command=command, generation=generation):
            world.submit(command, generation=generation)
        case ExecuteOperation(source="profile"):
            world.step()
        case FaultOperation(fault=fault, generation=generation):
            world.activate_fault(fault, generation=generation)
        case ObserveOperation(request=request, observation=observation, poll=poll):
            world.observe(request, generation=observation.generation, poll=poll)
        case CrashOperation(cut=cut, generation=generation):
            world.crash(cut, generation=generation)
        case RestartOperation():
            world.restart()
        case FairOperation(generation=generation):
            world.begin_fair(generation=generation)
        case FinishOperation(disposition=disposition, generation=generation):
            world.finish(Disposition(disposition), generation=generation)
        case FailureOperation(attempt=attempt):
            _replay_attempt(world, attempt)


def _replay_attempt(world: World, attempt: OperationAttempt) -> None:
    match attempt:
        case SubmitAttempt(command=command, generation=generation):
            world.submit(command, generation=generation)
        case StepAttempt():
            world.step()
        case FaultAttempt(fault=fault, generation=generation):
            world.activate_fault(fault, generation=generation)
        case ObserveAttempt(request=request, generation=generation, poll=poll):
            world.observe(request, generation=generation, poll=poll)
        case CrashAttempt(cut=cut, generation=generation):
            world.crash(cut, generation=generation)
        case RestartAttempt():
            world.restart()
        case FairAttempt(generation=generation):
            world.begin_fair(generation=generation)
        case FinishAttempt(disposition=disposition, generation=generation):
            world.finish(Disposition(disposition), generation=generation)


def _attempt_produced_operation(attempt: OperationAttempt, operation: ExpandedOperation) -> bool:
    match attempt, operation:
        case (
            SubmitAttempt(command=attempted, generation=attempted_generation),
            ExecuteOperation(source="authored", command=accepted, generation=accepted_generation),
        ):
            return attempted == accepted and attempted_generation == accepted_generation
        case StepAttempt(), ExecuteOperation(source="profile"):
            return True
        case (
            FaultAttempt(fault=attempted, generation=attempted_generation),
            FaultOperation(fault=accepted, generation=accepted_generation),
        ):
            return attempted == accepted and attempted_generation == accepted_generation
        case (
            ObserveAttempt(
                request=attempted,
                generation=attempted_generation,
                poll=attempted_poll,
            ),
            ObserveOperation(request=accepted, observation=observation, poll=accepted_poll),
        ):
            return (
                attempted == accepted
                and attempted_generation == observation.generation
                and attempted_poll == accepted_poll
            )
        case (
            CrashAttempt(cut=attempted_cut, generation=attempted_generation),
            CrashOperation(cut=accepted_cut, generation=accepted_generation),
        ):
            return attempted_cut == accepted_cut and attempted_generation == accepted_generation
        case RestartAttempt(), RestartOperation():
            return True
        case (
            FairAttempt(generation=attempted_generation),
            FairOperation(generation=accepted_generation),
        ):
            return attempted_generation == accepted_generation
        case (
            FinishAttempt(disposition=attempted, generation=attempted_generation),
            FinishOperation(disposition=accepted, generation=accepted_generation),
        ):
            return attempted == accepted and attempted_generation == accepted_generation
        case _:
            return False


def _identity_key(identity: ComponentIdentity) -> tuple[str, int, str]:
    return identity.name, identity.version, identity.digest


def _journal_digest(entries: list[JournalEntry] | tuple[JournalEntry, ...]) -> str:
    return digest_json([entry.model_dump(mode="json") for entry in entries])


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _refuse_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value}")


__all__ = [
    "API_COMPATIBILITY",
    "ARTIFACT_FORMAT",
    "ARTIFACT_VERSION",
    "LEGACY_API_COMPATIBILITY",
    "LEGACY_ARTIFACT_VERSION",
    "RESULT_FORMAT",
    "ActionDisposition",
    "AnyReplayResult",
    "AnyScenarioArtifact",
    "ApplyResult",
    "Budget",
    "BudgetExhausted",
    "BudgetFailure",
    "CheckResult",
    "Checker",
    "CheckerIdentity",
    "Command",
    "ComponentIdentity",
    "Disposition",
    "DstError",
    "ExecuteOperation",
    "FailureOperation",
    "Fault",
    "FaultDisposition",
    "GenerationStart",
    "InvariantViolation",
    "InvariantFailure",
    "JournalEntry",
    "Observation",
    "ObservationRequest",
    "PendingWork",
    "ProfileIdentity",
    "ReplayMismatch",
    "ReplayResult",
    "ReplayResultV1",
    "RunUntilFailed",
    "ScenarioArtifact",
    "ScenarioArtifactV1",
    "ScenarioContext",
    "ScenarioProfile",
    "ScenarioRegistry",
    "ScheduledCommand",
    "StaleGeneration",
    "Timeline",
    "World",
    "decode_artifact",
    "digest_json",
    "encode_artifact",
    "load_artifact",
    "replay",
]
