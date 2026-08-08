"""Exact Agent Program ownership descriptors and program-owned seams."""

from __future__ import annotations

import pytest

from petrus.agenticus.catalog.descriptor import DescriptorIdentity, DescriptorKind
from petrus.agenticus.program.descriptor import (
    AgentProgramDescriptor,
    ContinuationRequirement,
    ProgramOwnership,
)
from petrus.agenticus.program.seam import ProgramSeams
from petrus.agenticus.thread.identity import EpisodeId


def identity(kind: DescriptorKind, name: str) -> DescriptorIdentity:
    return DescriptorIdentity(kind, name, 1)


@pytest.mark.parametrize("ownership", tuple(ProgramOwnership))
def test_each_program_ownership_has_one_exact_serializable_descriptor(ownership: ProgramOwnership) -> None:
    source = identity(DescriptorKind.PROGRAM, "pi.provider-loop")
    continuation = identity(DescriptorKind.CONTINUATION, "pi.native")
    descriptor = AgentProgramDescriptor(
        identity=identity(DescriptorKind.PROGRAM, f"example.{ownership.value}"),
        ownership=ownership,
        accepts_fresh_start=False,
        accepted_continuations=(ContinuationRequirement(continuation, source),),
        produced_continuation=continuation,
        owns_steering=True,
        owns_evaluation=True,
    )

    assert AgentProgramDescriptor.from_data(descriptor.to_data()) == descriptor
    assert descriptor.to_data() == {
        "schema_version": 1,
        "identity": descriptor.identity.to_data(),
        "ownership": ownership.value,
        "accepts_fresh_start": False,
        "accepted_continuations": [
            {"identity": continuation.to_data(), "program": source.to_data()},
        ],
        "produced_continuation": continuation.to_data(),
        "owns_steering": True,
        "owns_evaluation": True,
    }


def test_program_owned_seams_preserve_their_native_payload_types() -> None:
    descriptor = AgentProgramDescriptor(
        identity=identity(DescriptorKind.PROGRAM, "net.guarded-loop"),
        ownership=ProgramOwnership.NET,
        owns_steering=True,
        owns_evaluation=True,
    )
    directives: list[dict[str, object]] = []

    def steer(_episode: EpisodeId, directive: dict[str, object]) -> None:
        directives.append(directive)

    def evaluate(_episode: EpisodeId, trace: tuple[str, ...]) -> dict[str, object]:
        return {"native_net_trace": trace, "score": 1}

    seams = ProgramSeams(descriptor, steering=steer, evaluator=evaluate)
    directive = {"transition": "pause-before-write", "tokens": ["approval"]}
    trace = ("model.called", "guard.passed", "append.accepted")

    assert seams.steering is not None
    assert seams.evaluator is not None
    seams.steering(EpisodeId("episode-1"), directive)
    assert seams.evaluator(EpisodeId("episode-1"), trace) == {"native_net_trace": trace, "score": 1}
    assert directives == [directive]


def test_program_seam_binding_must_match_descriptor_ownership() -> None:
    descriptor = AgentProgramDescriptor(
        identity=identity(DescriptorKind.PROGRAM, "provider.closed-loop"),
        ownership=ProgramOwnership.PROVIDER,
    )

    with pytest.raises(ValueError, match="does not own steering"):
        ProgramSeams(descriptor, steering=lambda _episode, _directive: None)

    missing = AgentProgramDescriptor(
        identity=identity(DescriptorKind.PROGRAM, "harness.steerable"),
        ownership=ProgramOwnership.HARNESS,
        owns_steering=True,
    )
    with pytest.raises(ValueError, match="requires a steering seam"):
        ProgramSeams(missing)
