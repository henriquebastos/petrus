"""Continuation compatibility is explicit and checked before execution."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from petrus.agenticus.catalog.descriptor import DescriptorIdentity, DescriptorKind
from petrus.agenticus.program.descriptor import (
    AgentProgramDescriptor,
    ContinuationRequirement,
    ProgramOwnership,
)
from petrus.agenticus.thread.continuation import (
    Continuation,
    ContinuationDescriptor,
    ContinuationTransitionError,
    IncompatibleContinuation,
    check_continuation_compatibility,
)
from petrus.agenticus.thread.identity import ContinuationId, EpisodeId, ThreadId
from petrus.agenticus.thread.lifecycle import EpisodeBudget, Thread


def identity(kind: DescriptorKind, name: str) -> DescriptorIdentity:
    return DescriptorIdentity(kind, name, 1)


def program(name: str, continuation_name: str) -> AgentProgramDescriptor:
    program_identity = identity(DescriptorKind.PROGRAM, name)
    continuation_identity = identity(DescriptorKind.CONTINUATION, continuation_name)
    return AgentProgramDescriptor(
        identity=program_identity,
        ownership=ProgramOwnership.HARNESS,
        accepted_continuations=(ContinuationRequirement(continuation_identity, program_identity),),
        produced_continuation=continuation_identity,
    )


def continuation_descriptor(name: str, program_name: str) -> ContinuationDescriptor:
    return ContinuationDescriptor(
        identity(DescriptorKind.CONTINUATION, name),
        identity(DescriptorKind.PROGRAM, program_name),
    )


def test_compatibility_table_never_infers_cross_program_portability() -> None:
    programs = (
        program("amp.provider", "amp.thread"),
        program("pi.harness", "pi.session-jsonl"),
        program("impetus.net", "impetus.marking-projection"),
    )
    continuations = (
        continuation_descriptor("amp.thread", "amp.provider"),
        continuation_descriptor("pi.session-jsonl", "pi.harness"),
        continuation_descriptor("impetus.marking-projection", "impetus.net"),
    )

    table = [
        [check_continuation_compatibility(candidate, continuation).compatible for continuation in continuations]
        for candidate in programs
    ]

    assert table == [
        [True, False, False],
        [False, True, False],
        [False, False, True],
    ]


def test_program_that_requires_a_continuation_refuses_a_fresh_start() -> None:
    descriptor = AgentProgramDescriptor(
        identity=identity(DescriptorKind.PROGRAM, "provider.resume-only"),
        ownership=ProgramOwnership.PROVIDER,
        accepts_fresh_start=False,
    )

    result = check_continuation_compatibility(descriptor, None)

    assert not result.compatible
    assert [(issue.code, issue.subject) for issue in result.issues] == [
        ("continuation-required", "provider.resume-only"),
    ]


@dataclass
class FakePiCodec:
    descriptor: ContinuationDescriptor
    payloads: dict[str, list[dict[str, object]]]
    loads: int = 0

    def load(self, continuation: Continuation) -> list[dict[str, object]]:
        self.loads += 1
        return self.payloads[continuation.state_reference]


def test_incompatible_continuation_fails_typed_before_codec_or_execution() -> None:
    amp_descriptor = continuation_descriptor("amp.thread", "amp.provider")
    amp_continuation = Continuation(
        ContinuationId("continuation-amp-1"),
        ThreadId("thread-1"),
        amp_descriptor,
        "opaque:amp:thread-9",
    )
    pi_descriptor = continuation_descriptor("pi.session-jsonl", "pi.harness")
    codec = FakePiCodec(pi_descriptor, {"opaque:pi:1": [{"role": "assistant", "content": "native"}]})
    thread = Thread(ThreadId("thread-1"), continuation=amp_continuation)
    executions = 0

    assert amp_continuation.state_reference not in repr(amp_continuation)
    with pytest.raises(IncompatibleContinuation) as raised:
        thread.start_episode(
            EpisodeId("episode-1"),
            program("pi.harness", "pi.session-jsonl"),
            identity(DescriptorKind.RUNTIME, "pi.application-owned"),
            EpisodeBudget(max_turns=2, max_accepted_appends=2),
        )
        codec.load(amp_continuation)
        executions += 1

    assert executions == 0
    assert codec.loads == 0
    assert raised.value.result.to_data() == {
        "schema_version": 1,
        "candidate": identity(DescriptorKind.PROGRAM, "pi.harness").to_data(),
        "issues": [{"code": "continuation-not-accepted", "subject": "amp.thread"}],
    }


def test_explicit_migration_requirement_can_accept_another_programs_continuation() -> None:
    source = identity(DescriptorKind.PROGRAM, "provider.native")
    continuation = identity(DescriptorKind.CONTINUATION, "provider.native-thread")
    migration = AgentProgramDescriptor(
        identity=identity(DescriptorKind.PROGRAM, "harness.migration"),
        ownership=ProgramOwnership.HARNESS,
        accepts_fresh_start=False,
        accepted_continuations=(ContinuationRequirement(continuation, source),),
    )

    assert check_continuation_compatibility(
        migration,
        ContinuationDescriptor(continuation, source),
    ).compatible
    mismatch = check_continuation_compatibility(
        migration,
        ContinuationDescriptor(continuation, identity(DescriptorKind.PROGRAM, "provider.lookalike")),
    )
    assert not mismatch.compatible
    assert [issue.code for issue in mismatch.issues] == ["continuation-program-mismatch"]


def test_continuation_revision_can_be_claimed_only_once() -> None:
    continuation = Continuation(
        ContinuationId("continuation-once"),
        ThreadId("thread-once"),
        continuation_descriptor("pi.session-jsonl", "pi.harness"),
        "opaque:pi:once",
    )

    claimed = continuation.claim()

    with pytest.raises(ContinuationTransitionError, match="in-use"):
        claimed.claim()
    with pytest.raises(ContinuationTransitionError, match="retired"):
        claimed.retire().claim()
