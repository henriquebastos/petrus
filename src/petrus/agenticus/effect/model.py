"""Strict provider-neutral values for proposing, fencing, and evidencing Effects."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum

_SCHEMA_VERSION = 1
_MAX_TEXT_BYTES = 256
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CODE = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")


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


def _code(value: object, name: str) -> str:
    value = _text(value, name)
    if _CODE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase dotted, dashed, or underscored code")
    return value


def _positive_integer(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _exact_object(value: object, fields: set[str], message: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise ValueError(message)
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _strict_json(value: object) -> None:
    if value is None or type(value) in {str, bool, int}:
        return
    if type(value) is list:
        for item in value:
            _strict_json(item)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("effect payload object keys must be strings")
            _strict_json(item)
        return
    raise TypeError(
        "effect payload must contain only strict JSON values; floating-point and extended Python values are forbidden"
    )


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _payload_copy(payload: object) -> dict[str, object]:
    if type(payload) is not dict:
        raise TypeError("effect payload must be a strict JSON object")
    _strict_json(payload)
    copied = json.loads(_canonical(payload))
    if type(copied) is not dict:
        raise AssertionError("canonical effect payload stopped being an object")
    return copied


def digest_payload(payload: object) -> str:
    """Return the canonical digest retained by proposals; raw payload bytes are not retained."""
    copied = _payload_copy(payload)
    return f"sha256:{hashlib.sha256(_canonical(copied)).hexdigest()}"


@dataclass(frozen=True, order=True)
class TargetIdentity:
    """Host-defined external target identity with no provider-specific type."""

    target_type: str
    target_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_type", _code(self.target_type, "target type"))
        object.__setattr__(self, "target_id", _text(self.target_id, "target id"))

    def to_data(self) -> dict[str, str]:
        return {"target_type": self.target_type, "target_id": self.target_id}

    @classmethod
    def from_data(cls, data: object) -> TargetIdentity:
        data = _exact_object(
            data,
            {"target_type", "target_id"},
            "target identity requires exact target_type and target_id fields",
        )
        return cls(_code(data["target_type"], "target type"), _text(data["target_id"], "target id"))


@dataclass(frozen=True)
class EffectProposal:
    """One secret-free proposal identity; a host keeps the raw payload separately."""

    proposal_id: str
    effect_type: str
    effect_version: int
    payload_digest: str
    target: TargetIdentity
    requested_authority_class: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_id", _text(self.proposal_id, "proposal id"))
        object.__setattr__(self, "effect_type", _code(self.effect_type, "effect type"))
        object.__setattr__(self, "effect_version", _positive_integer(self.effect_version, "effect version"))
        object.__setattr__(self, "payload_digest", _digest(self.payload_digest, "payload digest"))
        if not isinstance(self.target, TargetIdentity):
            raise TypeError("proposal target must be TargetIdentity")
        object.__setattr__(
            self,
            "requested_authority_class",
            _code(self.requested_authority_class, "requested authority class"),
        )

    def to_data(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "proposal_id": self.proposal_id,
            "effect_type": self.effect_type,
            "effect_version": self.effect_version,
            "payload_digest": self.payload_digest,
            "target": self.target.to_data(),
            "requested_authority_class": self.requested_authority_class,
        }

    @classmethod
    def from_data(cls, data: object) -> EffectProposal:
        data = _exact_object(
            data,
            {
                "schema_version",
                "proposal_id",
                "effect_type",
                "effect_version",
                "payload_digest",
                "target",
                "requested_authority_class",
            },
            "effect proposal requires exact version-1 fields",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError("effect proposal schema_version must be integer 1")
        return cls(
            _text(data["proposal_id"], "proposal id"),
            _code(data["effect_type"], "effect type"),
            _positive_integer(data["effect_version"], "effect version"),
            _digest(data["payload_digest"], "payload digest"),
            TargetIdentity.from_data(data["target"]),
            _code(data["requested_authority_class"], "requested authority class"),
        )

    @property
    def digest(self) -> str:
        """Bind approval and evidence to every exact field of this proposal."""
        return f"sha256:{hashlib.sha256(_canonical(self.to_data())).hexdigest()}"


@dataclass(frozen=True)
class EffectFence:
    """Frozen proposal, authority, target, Episode, and attachment preconditions."""

    proposal_id: str
    proposal_digest: str
    authority_epoch: int
    target_head: str
    episode_id: str
    attachment_id: str
    attachment_epoch: int

    def __post_init__(self) -> None:
        for name in ("proposal_id", "target_head", "episode_id", "attachment_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name.replace("_", " ")))
        object.__setattr__(self, "proposal_digest", _digest(self.proposal_digest, "proposal digest"))
        object.__setattr__(self, "authority_epoch", _positive_integer(self.authority_epoch, "authority epoch"))
        object.__setattr__(self, "attachment_epoch", _positive_integer(self.attachment_epoch, "attachment epoch"))

    def to_data(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "proposal_id": self.proposal_id,
            "proposal_digest": self.proposal_digest,
            "authority_epoch": self.authority_epoch,
            "target_head": self.target_head,
            "episode_id": self.episode_id,
            "attachment_id": self.attachment_id,
            "attachment_epoch": self.attachment_epoch,
        }

    @classmethod
    def from_data(cls, data: object) -> EffectFence:
        data = _exact_object(
            data,
            {
                "schema_version",
                "proposal_id",
                "proposal_digest",
                "authority_epoch",
                "target_head",
                "episode_id",
                "attachment_id",
                "attachment_epoch",
            },
            "effect fence requires exact version-1 fields",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError("effect fence schema_version must be integer 1")
        return cls(
            _text(data["proposal_id"], "proposal id"),
            _digest(data["proposal_digest"], "proposal digest"),
            _positive_integer(data["authority_epoch"], "authority epoch"),
            _text(data["target_head"], "target head"),
            _text(data["episode_id"], "episode id"),
            _text(data["attachment_id"], "attachment id"),
            _positive_integer(data["attachment_epoch"], "attachment epoch"),
        )

    def matches(self, proposal: EffectProposal) -> bool:
        return self.proposal_id == proposal.proposal_id and self.proposal_digest == proposal.digest


@dataclass(frozen=True)
class EffectReceipt:
    """Digest-only provider evidence correlated to one complete proposal identity."""

    proposal_id: str
    proposal_digest: str
    payload_digest: str
    target: TargetIdentity
    receipt_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_id", _text(self.proposal_id, "proposal id"))
        object.__setattr__(self, "proposal_digest", _digest(self.proposal_digest, "proposal digest"))
        object.__setattr__(self, "payload_digest", _digest(self.payload_digest, "payload digest"))
        if not isinstance(self.target, TargetIdentity):
            raise TypeError("effect receipt target must be TargetIdentity")
        object.__setattr__(self, "receipt_digest", _digest(self.receipt_digest, "receipt digest"))

    def correlates(self, proposal: EffectProposal) -> bool:
        return (
            self.proposal_id == proposal.proposal_id
            and self.proposal_digest == proposal.digest
            and self.payload_digest == proposal.payload_digest
            and self.target == proposal.target
        )

    def to_data(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "proposal_id": self.proposal_id,
            "proposal_digest": self.proposal_digest,
            "payload_digest": self.payload_digest,
            "target": self.target.to_data(),
            "receipt_digest": self.receipt_digest,
        }

    @classmethod
    def from_data(cls, data: object) -> EffectReceipt:
        data = _exact_object(
            data,
            {"schema_version", "proposal_id", "proposal_digest", "payload_digest", "target", "receipt_digest"},
            "effect receipt requires exact version-1 fields",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError("effect receipt schema_version must be integer 1")
        return cls(
            _text(data["proposal_id"], "proposal id"),
            _digest(data["proposal_digest"], "proposal digest"),
            _digest(data["payload_digest"], "payload digest"),
            TargetIdentity.from_data(data["target"]),
            _digest(data["receipt_digest"], "receipt digest"),
        )


class LookupDisposition(StrEnum):
    """A lookup- or fence-derived recovery classification before any retry."""

    APPLIED = "applied"
    SAFE_TO_RETRY = "safe-to-retry"
    SUPERSEDED = "superseded"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class LookupResult:
    """A lookup proof; only ``applied`` carries a correlated receipt."""

    disposition: LookupDisposition
    receipt: EffectReceipt | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, LookupDisposition):
            raise TypeError("lookup disposition must be LookupDisposition")
        if (self.disposition is LookupDisposition.APPLIED) != isinstance(self.receipt, EffectReceipt):
            raise ValueError("only an applied lookup requires an EffectReceipt")

    @classmethod
    def applied(cls, receipt: EffectReceipt) -> LookupResult:
        return cls(LookupDisposition.APPLIED, receipt)

    @classmethod
    def safe_to_retry(cls) -> LookupResult:
        return cls(LookupDisposition.SAFE_TO_RETRY)

    @classmethod
    def superseded(cls) -> LookupResult:
        return cls(LookupDisposition.SUPERSEDED)

    @classmethod
    def indeterminate(cls) -> LookupResult:
        return cls(LookupDisposition.INDETERMINATE)

    def to_data(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "disposition": self.disposition.value,
            "receipt": None if self.receipt is None else self.receipt.to_data(),
        }

    @classmethod
    def from_data(cls, data: object) -> LookupResult:
        data = _exact_object(
            data,
            {"schema_version", "disposition", "receipt"},
            "lookup result requires exact version-1 fields",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError("lookup result schema_version must be integer 1")
        try:
            disposition = LookupDisposition(data["disposition"])
        except (TypeError, ValueError) as error:
            raise ValueError("lookup disposition is not supported") from error
        receipt = data["receipt"]
        return cls(disposition, None if receipt is None else EffectReceipt.from_data(receipt))


@dataclass(frozen=True)
class EffectEvidence:
    """Secret-free exact correlation and lookup- or fence-derived recovery evidence."""

    proposal_id: str
    proposal_digest: str
    payload_digest: str
    target: TargetIdentity
    fence: EffectFence
    recovery: LookupDisposition | None
    receipt_digest: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_id", _text(self.proposal_id, "proposal id"))
        object.__setattr__(self, "proposal_digest", _digest(self.proposal_digest, "proposal digest"))
        object.__setattr__(self, "payload_digest", _digest(self.payload_digest, "payload digest"))
        if not isinstance(self.target, TargetIdentity):
            raise TypeError("effect evidence target must be TargetIdentity")
        if not isinstance(self.fence, EffectFence):
            raise TypeError("effect evidence fence must be EffectFence")
        if self.fence.proposal_id != self.proposal_id or self.fence.proposal_digest != self.proposal_digest:
            raise ValueError("effect evidence fence does not match its proposal")
        if self.recovery is not None and not isinstance(self.recovery, LookupDisposition):
            raise TypeError("effect evidence recovery must be LookupDisposition or None")
        if self.receipt_digest is not None:
            object.__setattr__(self, "receipt_digest", _digest(self.receipt_digest, "receipt digest"))
        has_receipt = self.receipt_digest is not None
        if self.recovery is LookupDisposition.APPLIED and not has_receipt:
            raise ValueError("applied evidence requires a receipt digest")
        if self.recovery not in {None, LookupDisposition.APPLIED} and has_receipt:
            raise ValueError("non-applied recovery evidence cannot carry a receipt digest")
        if self.recovery is None and not has_receipt:
            raise ValueError("direct execution evidence requires a receipt digest")

    def to_data(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "proposal_id": self.proposal_id,
            "proposal_digest": self.proposal_digest,
            "payload_digest": self.payload_digest,
            "target": self.target.to_data(),
            "fence": self.fence.to_data(),
            "recovery": None if self.recovery is None else self.recovery.value,
            "receipt_digest": self.receipt_digest,
        }

    @classmethod
    def from_data(cls, data: object) -> EffectEvidence:
        data = _exact_object(
            data,
            {
                "schema_version",
                "proposal_id",
                "proposal_digest",
                "payload_digest",
                "target",
                "fence",
                "recovery",
                "receipt_digest",
            },
            "effect evidence requires exact version-1 fields",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError("effect evidence schema_version must be integer 1")
        raw_recovery = data["recovery"]
        try:
            recovery = None if raw_recovery is None else LookupDisposition(raw_recovery)
        except (TypeError, ValueError) as error:
            raise ValueError("effect evidence recovery is not supported") from error
        raw_receipt = data["receipt_digest"]
        receipt = None if raw_receipt is None else _digest(raw_receipt, "receipt digest")
        return cls(
            _text(data["proposal_id"], "proposal id"),
            _digest(data["proposal_digest"], "proposal digest"),
            _digest(data["payload_digest"], "payload digest"),
            TargetIdentity.from_data(data["target"]),
            EffectFence.from_data(data["fence"]),
            recovery,
            receipt,
        )


class EffectDecisionKind(StrEnum):
    """Complete host decision vocabulary for a proposal lifecycle."""

    REJECT = "reject"
    APPROVE = "approve"
    EXECUTE = "execute"
    ALREADY_APPLIED = "already-applied"
    SUPERSEDED = "superseded"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class EffectDecision:
    """One exact host decision with impossible field combinations rejected."""

    kind: EffectDecisionKind
    proposal_id: str
    proposal_digest: str
    fence: EffectFence | None = None
    evidence: EffectEvidence | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EffectDecisionKind):
            raise TypeError("effect decision kind must be EffectDecisionKind")
        object.__setattr__(self, "proposal_id", _text(self.proposal_id, "proposal id"))
        object.__setattr__(self, "proposal_digest", _digest(self.proposal_digest, "proposal digest"))
        if self.reason_code is not None:
            object.__setattr__(self, "reason_code", _code(self.reason_code, "reason code"))
        if self.kind is EffectDecisionKind.REJECT:
            self._validate_rejection()
            return
        if self.kind is EffectDecisionKind.APPROVE:
            self._validate_approval()
        else:
            self._validate_outcome()
        self._validate_correlation()

    def _validate_rejection(self) -> None:
        if self.reason_code is None or self.fence is not None or self.evidence is not None:
            raise ValueError("reject requires only a secret-free reason code")

    def _validate_approval(self) -> None:
        if not isinstance(self.fence, EffectFence) or self.evidence is not None or self.reason_code is not None:
            raise ValueError("approve requires exactly one fence")

    def _validate_outcome(self) -> None:
        if (
            not isinstance(self.fence, EffectFence)
            or not isinstance(self.evidence, EffectEvidence)
            or self.reason_code is not None
        ):
            raise ValueError("execution decisions require exact fence and evidence values")
        expected_recovery = {
            EffectDecisionKind.EXECUTE: {None},
            EffectDecisionKind.ALREADY_APPLIED: {LookupDisposition.APPLIED},
            EffectDecisionKind.SUPERSEDED: {LookupDisposition.SUPERSEDED},
            EffectDecisionKind.INDETERMINATE: {
                LookupDisposition.SAFE_TO_RETRY,
                LookupDisposition.INDETERMINATE,
            },
        }
        if self.evidence.recovery not in expected_recovery[self.kind]:
            raise ValueError("effect evidence recovery does not match the decision kind")

    def _validate_correlation(self) -> None:
        if self.fence is None:
            raise AssertionError("non-rejection decision has no fence")
        if self.fence.proposal_id != self.proposal_id or self.fence.proposal_digest != self.proposal_digest:
            raise ValueError("effect decision fence does not match its proposal")
        if self.evidence is not None and (
            self.evidence.proposal_id != self.proposal_id
            or self.evidence.proposal_digest != self.proposal_digest
            or self.evidence.fence != self.fence
        ):
            raise ValueError("effect decision evidence does not match its proposal and fence")

    @classmethod
    def reject(cls, proposal: EffectProposal, reason_code: str) -> EffectDecision:
        if not isinstance(proposal, EffectProposal):
            raise TypeError("reject requires EffectProposal")
        return cls(EffectDecisionKind.REJECT, proposal.proposal_id, proposal.digest, reason_code=reason_code)

    @classmethod
    def approve(cls, proposal: EffectProposal, fence: EffectFence) -> EffectDecision:
        if not isinstance(proposal, EffectProposal):
            raise TypeError("approve requires EffectProposal")
        if not isinstance(fence, EffectFence) or not fence.matches(proposal):
            raise ValueError("approval fence does not match the proposal")
        return cls(EffectDecisionKind.APPROVE, proposal.proposal_id, proposal.digest, fence=fence)

    def to_data(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "kind": self.kind.value,
            "proposal_id": self.proposal_id,
            "proposal_digest": self.proposal_digest,
            "fence": None if self.fence is None else self.fence.to_data(),
            "evidence": None if self.evidence is None else self.evidence.to_data(),
            "reason_code": self.reason_code,
        }

    @classmethod
    def from_data(cls, data: object) -> EffectDecision:
        data = _exact_object(
            data,
            {"schema_version", "kind", "proposal_id", "proposal_digest", "fence", "evidence", "reason_code"},
            "effect decision requires exact version-1 fields",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError("effect decision schema_version must be integer 1")
        try:
            kind = EffectDecisionKind(data["kind"])
        except (TypeError, ValueError) as error:
            raise ValueError("effect decision kind is not supported") from error
        raw_fence, raw_evidence, raw_reason = data["fence"], data["evidence"], data["reason_code"]
        return cls(
            kind,
            _text(data["proposal_id"], "proposal id"),
            _digest(data["proposal_digest"], "proposal digest"),
            fence=None if raw_fence is None else EffectFence.from_data(raw_fence),
            evidence=None if raw_evidence is None else EffectEvidence.from_data(raw_evidence),
            reason_code=None if raw_reason is None else _code(raw_reason, "reason code"),
        )
