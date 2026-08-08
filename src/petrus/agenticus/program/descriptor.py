"""Provider-, harness-, and Net-owned Agent Program descriptors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from petrus.agenticus.catalog.descriptor import (
    DescriptorIdentity,
    DescriptorKind,
    _exact_object,
)

_SCHEMA_VERSION = 1


def _boolean(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{name} must be a boolean")
    return value


def _identity_of_kind(value: object, kind: DescriptorKind, name: str) -> DescriptorIdentity:
    if not isinstance(value, DescriptorIdentity) or value.kind is not kind:
        raise TypeError(f"{name} must be a {kind.value} DescriptorIdentity")
    return value


class ProgramOwnership(StrEnum):
    """The component that owns progression of an Agent Program."""

    PROVIDER = "provider-owned"
    HARNESS = "harness-owned"
    NET = "net-owned"


@dataclass(frozen=True, order=True)
class ContinuationRequirement:
    """One exact Continuation identity and the program that produced it."""

    identity: DescriptorIdentity
    program: DescriptorIdentity

    def __post_init__(self) -> None:
        _identity_of_kind(self.identity, DescriptorKind.CONTINUATION, "continuation requirement identity")
        _identity_of_kind(self.program, DescriptorKind.PROGRAM, "continuation requirement program")

    def to_data(self) -> dict[str, object]:
        return {"identity": self.identity.to_data(), "program": self.program.to_data()}

    @classmethod
    def from_data(cls, data: object) -> ContinuationRequirement:
        data = _exact_object(
            data,
            {"identity", "program"},
            "continuation requirement requires exact identity and program fields",
        )
        return cls(
            identity=DescriptorIdentity.from_data(data["identity"]),
            program=DescriptorIdentity.from_data(data["program"]),
        )


@dataclass(frozen=True)
class AgentProgramDescriptor:
    """Stable ownership and Continuation contract for one Agent Program."""

    identity: DescriptorIdentity
    ownership: ProgramOwnership
    accepts_fresh_start: bool = True
    accepted_continuations: tuple[ContinuationRequirement, ...] = ()
    produced_continuation: DescriptorIdentity | None = None
    owns_steering: bool = False
    owns_evaluation: bool = False

    def __post_init__(self) -> None:
        _identity_of_kind(self.identity, DescriptorKind.PROGRAM, "Agent Program identity")
        if not isinstance(self.ownership, ProgramOwnership):
            raise TypeError("Agent Program ownership must be ProgramOwnership")
        _boolean(self.accepts_fresh_start, "accepts_fresh_start")
        _boolean(self.owns_steering, "owns_steering")
        _boolean(self.owns_evaluation, "owns_evaluation")
        accepted = tuple(self.accepted_continuations)
        if any(not isinstance(requirement, ContinuationRequirement) for requirement in accepted):
            raise TypeError("accepted_continuations must contain ContinuationRequirement values")
        if len(set(accepted)) != len(accepted):
            raise ValueError("accepted_continuations must not contain duplicates")
        object.__setattr__(self, "accepted_continuations", tuple(sorted(accepted)))
        if self.produced_continuation is not None:
            _identity_of_kind(
                self.produced_continuation,
                DescriptorKind.CONTINUATION,
                "produced_continuation",
            )

    def to_data(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "identity": self.identity.to_data(),
            "ownership": self.ownership.value,
            "accepts_fresh_start": self.accepts_fresh_start,
            "accepted_continuations": [requirement.to_data() for requirement in self.accepted_continuations],
            "produced_continuation": (
                None if self.produced_continuation is None else self.produced_continuation.to_data()
            ),
            "owns_steering": self.owns_steering,
            "owns_evaluation": self.owns_evaluation,
        }

    @classmethod
    def from_data(cls, data: object) -> AgentProgramDescriptor:
        data = _exact_object(
            data,
            {
                "schema_version",
                "identity",
                "ownership",
                "accepts_fresh_start",
                "accepted_continuations",
                "produced_continuation",
                "owns_steering",
                "owns_evaluation",
            },
            "Agent Program descriptor requires its exact versioned fields",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError(f"Agent Program descriptor schema_version must be integer {_SCHEMA_VERSION}")
        try:
            ownership = ProgramOwnership(data["ownership"])
        except (TypeError, ValueError) as error:
            raise ValueError("Agent Program ownership is not supported") from error
        accepted = data["accepted_continuations"]
        if not isinstance(accepted, list):
            raise TypeError("accepted_continuations must be a JSON array")
        produced = data["produced_continuation"]
        return cls(
            identity=DescriptorIdentity.from_data(data["identity"]),
            ownership=ownership,
            accepts_fresh_start=_boolean(data["accepts_fresh_start"], "accepts_fresh_start"),
            accepted_continuations=tuple(ContinuationRequirement.from_data(item) for item in accepted),
            produced_continuation=None if produced is None else DescriptorIdentity.from_data(produced),
            owns_steering=_boolean(data["owns_steering"], "owns_steering"),
            owns_evaluation=_boolean(data["owns_evaluation"], "owns_evaluation"),
        )
