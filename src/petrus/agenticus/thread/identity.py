"""Runtime-distinct identities for Thread lifecycle values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

_MAX_TEXT_BYTES = 256


def _text(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > _MAX_TEXT_BYTES
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{name} must be a non-empty, trimmed string of at most {_MAX_TEXT_BYTES} UTF-8 bytes")
    return value


@dataclass(frozen=True)
class _LifecycleIdentity:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _text(self.value, f"{type(self).__name__} value"))

    def to_data(self) -> str:
        return self.value

    @classmethod
    def from_data(cls, data: object) -> Self:
        return cls(_text(data, f"{cls.__name__} value"))


class ThreadId(_LifecycleIdentity):
    """Durable identity of one Thread lineage."""


class ContinuationId(_LifecycleIdentity):
    """Identity of one resumable Continuation revision."""


class EpisodeId(_LifecycleIdentity):
    """Identity of one bounded Agent Program execution."""


class TurnId(_LifecycleIdentity):
    """Identity of one bounded progression step within an Episode."""
