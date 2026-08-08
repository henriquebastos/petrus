"""Maintained ES-049 seven-step application sensor/guard conformance policy.

This module is one host policy over the general grant and evidence
primitives, kept as the executable ES-049 conformance/example policy. The
gateway does not require it and hosts may bring their own sensors; nothing
here claims that every Episode must follow the seven-step shape.

The accepted ES-049 Episode performs at most eight one-turn appends: one
blocked write, then read, search, shell, a permitted write, the fixed test,
and one completion marker. The write grant may open only after read and
search have finalized, the marker is admitted only after a committed write
and a passing test, and any abort, deadline, stale result, or budget overrun
fails closed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from petrus.agenticus.hands.contract import RejectionCategory, ToolMethod, ToolResult

MAX_TURNS = 8

_FAIL_CLOSED = (RejectionCategory.ABORTED, RejectionCategory.DEADLINE)


class ConformanceError(RuntimeError):
    """The Episode exceeded a fail-closed conformance bound."""


@dataclass(frozen=True)
class MarkerDecision:
    """One admission decision for a proposed completion marker."""

    admitted: bool
    outcome: str

    @classmethod
    def complete(cls) -> MarkerDecision:
        return cls(admitted=True, outcome="episode_complete")

    @classmethod
    def step(cls) -> MarkerDecision:
        return cls(admitted=False, outcome="episode_step")


class SevenStepEpisodePolicy:
    """State-derived marker admission for one attachment epoch.

    The policy projects only finalized current-epoch tool results. Stale
    results are ignored, aborted or deadline results fail the Episode closed,
    and marker text alone can never complete an Episode.
    """

    def __init__(
        self,
        *,
        attachment_id: str,
        attachment_epoch: int,
        expected_marker: str,
        max_turns: int = MAX_TURNS,
        max_appends: int = MAX_TURNS,
    ) -> None:
        if not isinstance(attachment_id, str) or not attachment_id:
            raise ValueError("policy attachment_id must be a non-empty string")
        if type(attachment_epoch) is not int or attachment_epoch <= 0:
            raise ValueError("policy attachment_epoch must be a positive integer")
        if not isinstance(expected_marker, str) or not expected_marker:
            raise ValueError("policy expected_marker must be a non-empty string")
        for name, bound in (("max_turns", max_turns), ("max_appends", max_appends)):
            if type(bound) is not int or not (0 < bound <= MAX_TURNS) or not math.isfinite(bound):
                raise ValueError(f"policy {name} must be an integer between 1 and {MAX_TURNS}")
        self._attachment_id = attachment_id
        self._attachment_epoch = attachment_epoch
        self._expected_marker = expected_marker
        self._max_turns = max_turns
        self._max_appends = max_appends
        self._turns = 0
        self._appends = 0
        self._blocked_write_turn: int | None = None
        self._finalized: dict[ToolMethod, int] = {}
        self._grant_opened_turn: int | None = None
        self._write_committed_turn: int | None = None
        self._test_passed_turn: int | None = None
        self._premature_markers = 0
        self._failed = False

    @property
    def turns(self) -> int:
        return self._turns

    @property
    def appends(self) -> int:
        return self._appends

    @property
    def blocked_write_turn(self) -> int | None:
        return self._blocked_write_turn

    @property
    def grant_opened_turn(self) -> int | None:
        return self._grant_opened_turn

    @property
    def premature_markers(self) -> int:
        return self._premature_markers

    @property
    def failed(self) -> bool:
        return self._failed

    def finalized_turn(self, method: ToolMethod) -> int | None:
        return self._finalized.get(method)

    def begin_turn(self) -> int:
        """Start the next bounded one-tool-call turn or fail closed."""

        if self._turns >= self._max_turns:
            raise ConformanceError("episode exceeded its turn budget")
        self._turns += 1
        return self._turns

    def append_observation(self) -> int:
        """Count one caller-owned transcript append or fail closed."""

        if self._appends >= self._max_appends:
            raise ConformanceError("episode exceeded its append budget")
        self._appends += 1
        return self._appends

    def observe(self, method: ToolMethod, result: ToolResult) -> None:
        """Project one finalized result; stale results never contribute."""

        if not isinstance(method, ToolMethod) or not isinstance(result, ToolResult):
            raise TypeError("policy observation requires ToolMethod and ToolResult")
        if result.attachment_id != self._attachment_id or result.epoch != self._attachment_epoch:
            return
        if not result.ok:
            error = result.error
            if error is not None and error.category in _FAIL_CLOSED:
                self._failed = True
            if (
                method is ToolMethod.WORKSPACE_WRITE
                and error is not None
                and error.category is RejectionCategory.WRITE
                and self._grant_opened_turn is None
                and self._blocked_write_turn is None
            ):
                self._blocked_write_turn = self._turns
            return
        self._finalized.setdefault(method, self._turns)
        if method is ToolMethod.WORKSPACE_WRITE and self._grant_opened_turn is not None:
            self._write_committed_turn = self._turns
        if method is ToolMethod.WORKSPACE_TEST:
            data = result.data or {}
            if data.get("passed") is True:
                self._test_passed_turn = self._turns

    @property
    def write_grant_ready(self) -> bool:
        """Whether finalized read plus search permit opening the write grant."""

        return (
            not self._failed
            and self._grant_opened_turn is None
            and ToolMethod.WORKSPACE_READ in self._finalized
            and ToolMethod.WORKSPACE_SEARCH in self._finalized
        )

    def note_grant_opened(self) -> None:
        """Record that the host opened the write grant for this epoch."""

        if not self.write_grant_ready:
            raise ConformanceError("write grant requires prior finalized read and search")
        self._grant_opened_turn = self._turns

    def admit_marker(self, marker: str) -> MarkerDecision:
        """Admit a completion marker only from proven current-epoch state."""

        read_turn = self._finalized.get(ToolMethod.WORKSPACE_READ)
        search_turn = self._finalized.get(ToolMethod.WORKSPACE_SEARCH)
        ready = (
            marker == self._expected_marker
            and not self._failed
            and self._turns <= self._max_turns
            and self._blocked_write_turn is not None
            and self._grant_opened_turn is not None
            and read_turn is not None
            and search_turn is not None
            and read_turn <= self._grant_opened_turn
            and search_turn <= self._grant_opened_turn
            and self._write_committed_turn is not None
            and self._write_committed_turn > self._grant_opened_turn
            and self._test_passed_turn is not None
            and self._test_passed_turn > self._write_committed_turn
        )
        if not ready:
            self._premature_markers += 1
            return MarkerDecision.step()
        return MarkerDecision.complete()


__all__ = ["MAX_TURNS", "ConformanceError", "MarkerDecision", "SevenStepEpisodePolicy"]
