"""Minimal program-owned steering and evaluation seams."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from petrus.agenticus.program.descriptor import AgentProgramDescriptor
from petrus.agenticus.thread.identity import EpisodeId


class ProgramSteering[DirectiveT](Protocol):
    """Apply one program-native steering directive to an Episode."""

    def __call__(self, episode: EpisodeId, directive: DirectiveT, /) -> None: ...


class ProgramEvaluator[TraceT, EvaluationT](Protocol):
    """Evaluate one program-native trace without defining a trace schema."""

    def __call__(self, episode: EpisodeId, trace: TraceT, /) -> EvaluationT: ...


@dataclass(frozen=True)
class ProgramSeams[DirectiveT, TraceT, EvaluationT]:
    """Concrete optional seams whose ownership is declared by the program."""

    descriptor: AgentProgramDescriptor
    steering: ProgramSteering[DirectiveT] | None = None
    evaluator: ProgramEvaluator[TraceT, EvaluationT] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor, AgentProgramDescriptor):
            raise TypeError("program seams descriptor must be AgentProgramDescriptor")
        if self.descriptor.owns_steering and self.steering is None:
            raise ValueError("Agent Program requires a steering seam")
        if not self.descriptor.owns_steering and self.steering is not None:
            raise ValueError("Agent Program does not own steering")
        if self.descriptor.owns_evaluation and self.evaluator is None:
            raise ValueError("Agent Program requires an evaluator seam")
        if not self.descriptor.owns_evaluation and self.evaluator is not None:
            raise ValueError("Agent Program does not own evaluation")
