"""Immutable lifecycle-scope identity."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class LifecycleScope:
    """One exact named lifecycle generation."""

    name: str
    generation: int

    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name or "\x00" in self.name:
            raise ValueError(
                "LifecycleScope name must be a non-empty string without NUL and use the exact built-in type"
            )
        if type(self.generation) is not int or self.generation < 1:
            raise ValueError("LifecycleScope generation must be a positive integer of the exact built-in type")


__all__ = ["LifecycleScope"]
