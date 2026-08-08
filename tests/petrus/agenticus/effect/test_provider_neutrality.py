"""Differently shaped host adapters exercise one neutral Effect gateway."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from petrus.agenticus.effect.gateway import EffectGateway
from petrus.agenticus.effect.model import (
    EffectDecision,
    EffectDecisionKind,
    EffectFence,
    EffectProposal,
    EffectReceipt,
    LookupResult,
    TargetIdentity,
    digest_payload,
)


def _proposal(effect_type: str, target: TargetIdentity, authority: str, payload: dict[str, object]) -> EffectProposal:
    return EffectProposal("operation-42", effect_type, 1, digest_payload(payload), target, authority)


def _fence(proposal: EffectProposal) -> EffectFence:
    return EffectFence(proposal.proposal_id, proposal.digest, 7, "target-v3", "episode-5", "attachment-2", 1)


def _receipt(proposal: EffectProposal, evidence: dict[str, object]) -> EffectReceipt:
    return EffectReceipt(
        proposal.proposal_id,
        proposal.digest,
        proposal.payload_digest,
        proposal.target,
        digest_payload(evidence),
    )


class BulletinAdapter:
    """Append-only message-board provider with operation markers inside entries."""

    def __init__(self):
        self.entries: list[dict[str, str]] = []
        self.calls: list[str] = []

    def lookup(self, proposal: EffectProposal) -> LookupResult:
        self.calls.append("lookup")
        entry = next((item for item in self.entries if item["operation"] == proposal.proposal_id), None)
        if entry is None:
            return LookupResult.safe_to_retry()
        if entry["payload_digest"] != proposal.payload_digest:
            return LookupResult.indeterminate()
        return LookupResult.applied(_receipt(proposal, {"entry": entry["entry_id"]}))

    def execute(self, proposal: EffectProposal, payload: dict[str, object], fence: EffectFence) -> EffectReceipt:
        self.calls.append("execute")
        entry_id = f"entry-{len(self.entries) + 1}"
        self.entries.append(
            {
                "entry_id": entry_id,
                "operation": proposal.proposal_id,
                "payload_digest": proposal.payload_digest,
                "message": str(payload["message"]),
            }
        )
        return _receipt(proposal, {"entry": entry_id})


class DeploymentAdapter:
    """Compare-and-swap deployment provider keyed by service and generation."""

    def __init__(self):
        self.services: dict[str, dict[str, object]] = {}
        self.calls: list[str] = []

    def lookup(self, proposal: EffectProposal) -> LookupResult:
        self.calls.append("lookup")
        deployment = self.services.get(proposal.target.target_id)
        if deployment is None or deployment["operation"] != proposal.proposal_id:
            return LookupResult.safe_to_retry()
        if deployment["digest"] != proposal.payload_digest:
            return LookupResult.indeterminate()
        return LookupResult.applied(_receipt(proposal, {"generation": deployment["generation"]}))

    def execute(self, proposal: EffectProposal, payload: dict[str, object], fence: EffectFence) -> EffectReceipt:
        self.calls.append("execute")
        generation = int(self.services.get(proposal.target.target_id, {}).get("generation", 0)) + 1
        self.services[proposal.target.target_id] = {
            "operation": proposal.proposal_id,
            "digest": proposal.payload_digest,
            "generation": generation,
            "release": payload["release"],
            "regions": payload["regions"],
        }
        return _receipt(proposal, {"generation": generation})


class FenceSource:
    def __init__(self, fence: EffectFence):
        self.fence = fence

    def current(self, proposal: EffectProposal) -> EffectFence:
        return self.fence


@pytest.mark.parametrize(
    ("adapter_factory", "proposal_factory", "payload", "effect_count"),
    (
        (
            BulletinAdapter,
            lambda payload: _proposal(
                "bulletin.publish", TargetIdentity("bulletin", "release-notes"), "communications.publish", payload
            ),
            {"message": "Version 1 is ready"},
            lambda adapter: len(adapter.entries),
        ),
        (
            DeploymentAdapter,
            lambda payload: _proposal(
                "deployment.rollout", TargetIdentity("service", "payments"), "deployment.production", payload
            ),
            {"release": {"image": "registry.invalid/app@sha256:abc"}, "regions": ["west", "north"]},
            lambda adapter: len(adapter.services),
        ),
    ),
)
def test_two_provider_shapes_execute_once_and_replay_lookup_first(
    adapter_factory: Callable[[], object],
    proposal_factory: Callable[[dict[str, object]], EffectProposal],
    payload: dict[str, object],
    effect_count: Callable[[object], int],
) -> None:
    adapter = adapter_factory()
    proposal = proposal_factory(payload)
    fence = _fence(proposal)
    gateway = EffectGateway(adapter, FenceSource(fence))
    approval = EffectDecision.approve(proposal, fence)

    executed = gateway.execute(proposal, payload, approval)
    replayed = gateway.execute(proposal, payload, approval)

    assert executed.kind is EffectDecisionKind.EXECUTE
    assert replayed.kind is EffectDecisionKind.ALREADY_APPLIED
    assert effect_count(adapter) == 1
    assert adapter.calls == ["lookup", "execute", "lookup"]
    for decision in (executed, replayed):
        assert decision.proposal_id == proposal.proposal_id
        assert decision.proposal_digest == proposal.digest
        assert decision.evidence is not None
        assert decision.evidence.payload_digest == proposal.payload_digest
        assert decision.evidence.target == proposal.target


def test_provider_side_compare_and_swap_race_resolves_superseded_without_second_effect() -> None:
    payload = {"release": {"image": "registry.invalid/app@sha256:abc"}, "regions": ["west"]}
    proposal = _proposal("deployment.rollout", TargetIdentity("service", "payments"), "deployment.production", payload)
    fence = _fence(proposal)

    class RacingDeployment(DeploymentAdapter):
        def __init__(self):
            super().__init__()
            self.raced = False

        def lookup(self, proposal: EffectProposal) -> LookupResult:
            if self.raced:
                self.calls.append("lookup")
                return LookupResult.superseded()
            return super().lookup(proposal)

        def execute(self, proposal: EffectProposal, payload: dict[str, object], fence: EffectFence) -> EffectReceipt:
            self.calls.append("execute")
            self.raced = True
            raise RuntimeError("provider compare-and-swap rejected stale target head")

    adapter = RacingDeployment()
    decision = EffectGateway(adapter, FenceSource(fence)).execute(
        proposal,
        payload,
        EffectDecision.approve(proposal, fence),
    )

    assert decision.kind is EffectDecisionKind.SUPERSEDED
    assert adapter.calls == ["lookup", "execute", "lookup"]
    assert adapter.services == {}
