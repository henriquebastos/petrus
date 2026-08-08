"""Lifecycle-only candidate results from provider/profile-specific runtimes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from petrus.agenticus.thread.identity import EpisodeId, TurnId
from petrus.agenticus.thread.lifecycle import TurnOutcome

_MAX_REFERENCE_BYTES = 512
_TERMINATION_CODE = re.compile(r"[a-z][a-z0-9.-]{0,127}")


def _reference(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > _MAX_REFERENCE_BYTES
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{name} must be a bounded non-empty opaque reference")
    return value


def _optional_reference(value: object, name: str) -> str | None:
    return None if value is None else _reference(value, name)


def safe_termination_code(value: object) -> str:
    """Validate one machine-safe code suitable for lifecycle evidence."""

    if not isinstance(value, str) or _TERMINATION_CODE.fullmatch(value) is None:
        raise ValueError("runtime termination code must be a bounded lowercase machine token")
    return value


@dataclass(frozen=True)
class RuntimeTurnSettlement:
    """A candidate host result, not authority to settle a DS3 Turn or Episode.

    One accepted append is one complete runtime Turn batch. Provider messages,
    prompts, tool bodies, usage bodies, authority, paths, and raw diagnostics
    remain behind the opaque references and profile-specific custody.
    """

    episode_id: EpisodeId
    turn_id: TurnId
    outcome: TurnOutcome
    accepted_appends: int
    termination_code: str
    output_reference: str | None = field(default=None, repr=False)
    continuation_reference: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.episode_id, EpisodeId):
            raise TypeError("runtime result episode_id must be EpisodeId")
        if not isinstance(self.turn_id, TurnId):
            raise TypeError("runtime result turn_id must be TurnId")
        if not isinstance(self.outcome, TurnOutcome):
            raise TypeError("runtime result outcome must be TurnOutcome")
        if type(self.accepted_appends) is not int or self.accepted_appends not in (0, 1):
            raise ValueError("runtime result accepted_appends must be zero or one complete Turn batch")
        if self.outcome is TurnOutcome.COMPLETED and self.accepted_appends != 1:
            raise ValueError("a completed runtime Turn requires its one complete accepted append")
        object.__setattr__(self, "termination_code", safe_termination_code(self.termination_code))
        object.__setattr__(
            self,
            "output_reference",
            _optional_reference(self.output_reference, "runtime output_reference"),
        )
        object.__setattr__(
            self,
            "continuation_reference",
            _optional_reference(self.continuation_reference, "runtime continuation_reference"),
        )
