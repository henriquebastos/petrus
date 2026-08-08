"""Shared result shape for compatibility checks."""

from __future__ import annotations

from dataclasses import dataclass

from petrus.agenticus.catalog.descriptor import DescriptorIdentity, _exact_object, _text

_SCHEMA_VERSION = 1


@dataclass(frozen=True, order=True)
class CompatibilityIssue:
    """One machine-readable incompatibility with an opaque safe subject."""

    code: str
    subject: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _text(self.code, "compatibility issue code"))
        object.__setattr__(self, "subject", _text(self.subject, "compatibility issue subject"))

    def to_data(self) -> dict[str, str]:
        return {"code": self.code, "subject": self.subject}

    @classmethod
    def from_data(cls, data: object) -> CompatibilityIssue:
        data = _exact_object(
            data,
            {"code", "subject"},
            "compatibility issue requires exact code and subject fields",
        )
        return cls(
            code=_text(data["code"], "compatibility issue code"),
            subject=_text(data["subject"], "compatibility issue subject"),
        )


@dataclass(frozen=True)
class CompatibilityResult:
    """A candidate-local compatibility result; success is structurally derived."""

    candidate: DescriptorIdentity | None
    issues: tuple[CompatibilityIssue, ...] = ()

    def __post_init__(self) -> None:
        if self.candidate is not None and not isinstance(self.candidate, DescriptorIdentity):
            raise TypeError("compatibility candidate must be DescriptorIdentity or None")
        issues = tuple(self.issues)
        if any(not isinstance(issue, CompatibilityIssue) for issue in issues):
            raise TypeError("compatibility issues must contain CompatibilityIssue values")
        if len(set(issues)) != len(issues):
            raise ValueError("compatibility issues must not contain duplicates")
        if self.candidate is None and not issues:
            raise ValueError("a compatible result requires a candidate")
        object.__setattr__(self, "issues", tuple(sorted(issues)))

    @property
    def compatible(self) -> bool:
        return self.candidate is not None and not self.issues

    def to_data(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "candidate": None if self.candidate is None else self.candidate.to_data(),
            "issues": [issue.to_data() for issue in self.issues],
        }

    @classmethod
    def from_data(cls, data: object) -> CompatibilityResult:
        data = _exact_object(
            data,
            {"schema_version", "candidate", "issues"},
            "compatibility result requires exact schema_version, candidate, and issues fields",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError(f"compatibility result schema_version must be integer {_SCHEMA_VERSION}")
        issues = data["issues"]
        if not isinstance(issues, list):
            raise TypeError("compatibility result issues must be a JSON array")
        candidate = data["candidate"]
        return cls(
            candidate=None if candidate is None else DescriptorIdentity.from_data(candidate),
            issues=tuple(CompatibilityIssue.from_data(issue) for issue in issues),
        )
