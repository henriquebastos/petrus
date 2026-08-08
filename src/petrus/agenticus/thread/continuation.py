"""Opaque Continuation custody and explicit Agent Program compatibility."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Protocol

from petrus.agenticus.catalog.descriptor import (
    DescriptorIdentity,
    DescriptorKind,
    _exact_object,
)
from petrus.agenticus.catalog.result import CompatibilityIssue, CompatibilityResult
from petrus.agenticus.program.descriptor import AgentProgramDescriptor
from petrus.agenticus.thread.identity import ContinuationId, ThreadId, _text

_SCHEMA_VERSION = 1


def _identity_of_kind(value: object, kind: DescriptorKind, name: str) -> DescriptorIdentity:
    if not isinstance(value, DescriptorIdentity) or value.kind is not kind:
        raise TypeError(f"{name} must be a {kind.value} DescriptorIdentity")
    return value


class ContinuationState(StrEnum):
    """Custody state of one immutable Continuation revision."""

    AVAILABLE = "available"
    IN_USE = "in-use"
    RETIRED = "retired"


class ContinuationTransitionError(ValueError):
    """A requested Continuation transition is not valid from its current state."""


@dataclass(frozen=True, order=True)
class ContinuationDescriptor:
    """The exact provider/program-specific contract behind opaque state."""

    identity: DescriptorIdentity
    program: DescriptorIdentity

    def __post_init__(self) -> None:
        _identity_of_kind(self.identity, DescriptorKind.CONTINUATION, "Continuation descriptor identity")
        _identity_of_kind(self.program, DescriptorKind.PROGRAM, "Continuation descriptor program")

    def to_data(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "identity": self.identity.to_data(),
            "program": self.program.to_data(),
        }

    @classmethod
    def from_data(cls, data: object) -> ContinuationDescriptor:
        data = _exact_object(
            data,
            {"schema_version", "identity", "program"},
            "Continuation descriptor requires exact schema_version, identity, and program fields",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError(f"Continuation descriptor schema_version must be integer {_SCHEMA_VERSION}")
        return cls(
            identity=DescriptorIdentity.from_data(data["identity"]),
            program=DescriptorIdentity.from_data(data["program"]),
        )


@dataclass(frozen=True)
class Continuation:
    """A lifecycle envelope around an opaque provider/program custody reference."""

    id: ContinuationId
    thread: ThreadId
    descriptor: ContinuationDescriptor
    state_reference: str = field(repr=False)
    state: ContinuationState = ContinuationState.AVAILABLE

    def __post_init__(self) -> None:
        if not isinstance(self.id, ContinuationId):
            raise TypeError("Continuation id must be ContinuationId")
        if not isinstance(self.thread, ThreadId):
            raise TypeError("Continuation thread must be ThreadId")
        if not isinstance(self.descriptor, ContinuationDescriptor):
            raise TypeError("Continuation descriptor must be ContinuationDescriptor")
        object.__setattr__(self, "state_reference", _text(self.state_reference, "Continuation state_reference"))
        if not isinstance(self.state, ContinuationState):
            raise TypeError("Continuation state must be ContinuationState")

    def claim(self) -> Continuation:
        if self.state is not ContinuationState.AVAILABLE:
            raise ContinuationTransitionError(f"cannot claim a Continuation in {self.state.value} state")
        return replace(self, state=ContinuationState.IN_USE)

    def retire(self) -> Continuation:
        if self.state is ContinuationState.RETIRED:
            return self
        return replace(self, state=ContinuationState.RETIRED)

    def to_data(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "id": self.id.to_data(),
            "thread": self.thread.to_data(),
            "descriptor": self.descriptor.to_data(),
            "state_reference": self.state_reference,
            "state": self.state.value,
        }

    @classmethod
    def from_data(cls, data: object) -> Continuation:
        data = _exact_object(
            data,
            {"schema_version", "id", "thread", "descriptor", "state_reference", "state"},
            "Continuation requires its exact versioned fields",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError(f"Continuation schema_version must be integer {_SCHEMA_VERSION}")
        try:
            state = ContinuationState(data["state"])
        except (TypeError, ValueError) as error:
            raise ValueError("Continuation state is not supported") from error
        return cls(
            id=ContinuationId.from_data(data["id"]),
            thread=ThreadId.from_data(data["thread"]),
            descriptor=ContinuationDescriptor.from_data(data["descriptor"]),
            state_reference=_text(data["state_reference"], "Continuation state_reference"),
            state=state,
        )


class ContinuationCodec[PayloadT](Protocol):
    """Resolve one profile-specific payload without exposing it to Thread values."""

    descriptor: ContinuationDescriptor

    def load(self, continuation: Continuation, /) -> PayloadT: ...


class IncompatibleContinuation(ValueError):
    """Typed refusal raised before a Continuation is resolved or executed."""

    def __init__(self, result: CompatibilityResult) -> None:
        self.result = result
        issues = ", ".join(issue.code for issue in result.issues)
        super().__init__(f"Continuation is incompatible with Agent Program: {issues}")


def check_continuation_compatibility(
    program: AgentProgramDescriptor,
    continuation: ContinuationDescriptor | None,
) -> CompatibilityResult:
    """Check only explicit descriptor-table entries; never translate state."""

    if continuation is None:
        issues = (
            () if program.accepts_fresh_start else (CompatibilityIssue("continuation-required", program.identity.name),)
        )
        return CompatibilityResult(candidate=program.identity, issues=issues)

    matching_identity = tuple(
        requirement for requirement in program.accepted_continuations if requirement.identity == continuation.identity
    )
    if not matching_identity:
        issues = (CompatibilityIssue("continuation-not-accepted", continuation.identity.name),)
    elif not any(requirement.program == continuation.program for requirement in matching_identity):
        issues = (CompatibilityIssue("continuation-program-mismatch", continuation.program.name),)
    else:
        issues = ()
    return CompatibilityResult(candidate=program.identity, issues=issues)


def require_continuation_compatible(
    program: AgentProgramDescriptor,
    continuation: ContinuationDescriptor | None,
) -> None:
    result = check_continuation_compatibility(program, continuation)
    if not result.compatible:
        raise IncompatibleContinuation(result)
