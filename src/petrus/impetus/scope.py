"""Immutable lifecycle-scope identity."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class LifecycleScope:
    """One exact named lifecycle generation."""

    name: str
    generation: int

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name or "\x00" in self.name:
            raise ValueError("LifecycleScope name must be a non-empty string without NUL")
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation < 1:
            raise ValueError("LifecycleScope generation must be a positive integer")


__all__ = ["LifecycleScope"]
