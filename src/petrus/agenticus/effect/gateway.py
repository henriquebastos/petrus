"""Lookup-first host gateway for provider-neutral external Effects.

Workspace mutation belongs to Agenticus Hands. This gateway accepts only a
host-approved external Effect proposal and never retries one provider execution
inside the same call: every uncertain response is reconciled by lookup first.
"""

from __future__ import annotations

from typing import Protocol

from petrus.agenticus.effect.model import (
    EffectDecision,
    EffectDecisionKind,
    EffectEvidence,
    EffectFence,
    EffectProposal,
    EffectReceipt,
    LookupDisposition,
    LookupResult,
    _payload_copy,
    digest_payload,
)


class EffectAdapter(Protocol):
    """Host adapter that owns provider lookup and native conditional mutation."""

    def lookup(self, proposal: EffectProposal) -> LookupResult: ...

    def execute(self, proposal: EffectProposal, payload: dict[str, object], fence: EffectFence) -> EffectReceipt:
        """Execute once, enforcing the provider's native target-head condition from ``fence``."""
        ...


class EffectFenceSource(Protocol):
    """Host authority that refreshes all current fence coordinates together."""

    def current(self, proposal: EffectProposal) -> EffectFence: ...


class EffectGateway:
    """Correlate approval, lookup, fresh fences, one execution, and digest-only evidence."""

    def __init__(self, adapter: EffectAdapter, fences: EffectFenceSource):
        self._adapter = adapter
        self._fences = fences

    def execute(
        self,
        proposal: EffectProposal,
        payload: object,
        approval: EffectDecision,
    ) -> EffectDecision:
        """Execute at most once after lookup and fresh fences; reconcile uncertainty without blind retry."""
        fence = self._approval_fence(proposal, approval)
        copied_payload = _payload_copy(payload)
        if digest_payload(copied_payload) != proposal.payload_digest:
            raise ValueError("effect payload digest does not match the proposal")

        resolved = self._lookup_decision(proposal, fence, self._lookup(proposal))
        if resolved is not None:
            return resolved
        current = self._current(proposal)
        if current is None:
            return self._outcome(
                proposal,
                fence,
                EffectDecisionKind.INDETERMINATE,
                LookupDisposition.SAFE_TO_RETRY,
            )
        if current != fence:
            return self._outcome(proposal, fence, EffectDecisionKind.SUPERSEDED, LookupDisposition.SUPERSEDED)
        return self._execute_once(proposal, copied_payload, fence)

    @staticmethod
    def _approval_fence(proposal: EffectProposal, approval: EffectDecision) -> EffectFence:
        if not isinstance(proposal, EffectProposal):
            raise TypeError("effect gateway requires EffectProposal")
        if not isinstance(approval, EffectDecision) or approval.kind is not EffectDecisionKind.APPROVE:
            raise TypeError("effect gateway requires an approved EffectDecision")
        if approval.proposal_id != proposal.proposal_id or approval.proposal_digest != proposal.digest:
            raise ValueError("effect approval does not match the proposal")
        if approval.fence is None:
            raise AssertionError("approved effect decision has no fence")
        return approval.fence

    def _execute_once(
        self,
        proposal: EffectProposal,
        payload: dict[str, object],
        fence: EffectFence,
    ) -> EffectDecision:
        try:
            receipt = self._adapter.execute(proposal, payload, fence)
        except Exception:
            return self._recover(proposal, fence)
        if not isinstance(receipt, EffectReceipt) or not receipt.correlates(proposal):
            return self._recover(proposal, fence)
        return self._outcome(proposal, fence, EffectDecisionKind.EXECUTE, None, receipt)

    def _lookup_decision(
        self,
        proposal: EffectProposal,
        fence: EffectFence,
        lookup: LookupResult,
    ) -> EffectDecision | None:
        if lookup.disposition is LookupDisposition.SAFE_TO_RETRY:
            return None
        if lookup.disposition is LookupDisposition.APPLIED:
            return self._applied_or_indeterminate(proposal, fence, lookup)
        kind = (
            EffectDecisionKind.SUPERSEDED
            if lookup.disposition is LookupDisposition.SUPERSEDED
            else EffectDecisionKind.INDETERMINATE
        )
        return self._outcome(proposal, fence, kind, lookup.disposition)

    def _recover(self, proposal: EffectProposal, fence: EffectFence) -> EffectDecision:
        lookup = self._lookup(proposal)
        if lookup.disposition is LookupDisposition.APPLIED:
            return self._applied_or_indeterminate(proposal, fence, lookup)
        kind = (
            EffectDecisionKind.SUPERSEDED
            if lookup.disposition is LookupDisposition.SUPERSEDED
            else EffectDecisionKind.INDETERMINATE
        )
        return self._outcome(proposal, fence, kind, lookup.disposition)

    def _applied_or_indeterminate(
        self,
        proposal: EffectProposal,
        fence: EffectFence,
        lookup: LookupResult,
    ) -> EffectDecision:
        receipt = lookup.receipt
        if receipt is None or not receipt.correlates(proposal):
            return self._outcome(
                proposal,
                fence,
                EffectDecisionKind.INDETERMINATE,
                LookupDisposition.INDETERMINATE,
            )
        return self._outcome(
            proposal,
            fence,
            EffectDecisionKind.ALREADY_APPLIED,
            LookupDisposition.APPLIED,
            receipt,
        )

    def _lookup(self, proposal: EffectProposal) -> LookupResult:
        try:
            result = self._adapter.lookup(proposal)
        except Exception:
            return LookupResult.indeterminate()
        return result if isinstance(result, LookupResult) else LookupResult.indeterminate()

    def _current(self, proposal: EffectProposal) -> EffectFence | None:
        try:
            current = self._fences.current(proposal)
        except Exception:
            return None
        return current if isinstance(current, EffectFence) else None

    @staticmethod
    def _outcome(
        proposal: EffectProposal,
        fence: EffectFence,
        kind: EffectDecisionKind,
        recovery: LookupDisposition | None,
        receipt: EffectReceipt | None = None,
    ) -> EffectDecision:
        evidence = EffectEvidence(
            proposal.proposal_id,
            proposal.digest,
            proposal.payload_digest,
            proposal.target,
            fence,
            recovery,
            None if receipt is None else receipt.receipt_digest,
        )
        return EffectDecision(kind, proposal.proposal_id, proposal.digest, fence=fence, evidence=evidence)
