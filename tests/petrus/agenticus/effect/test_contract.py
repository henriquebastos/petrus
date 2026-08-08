"""Strict provider-neutral Effect proposal, decision, and evidence values."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from hypothesis import given, settings, strategies as st

from petrus.agenticus.effect.gateway import EffectGateway
from petrus.agenticus.effect.model import (
    EffectDecision,
    EffectDecisionKind,
    EffectEvidence,
    EffectFence,
    EffectProposal,
    EffectReceipt,
    LookupDisposition,
    LookupResult,
    TargetIdentity,
    digest_payload,
)


def _proposal(payload: object | None = None) -> EffectProposal:
    return EffectProposal(
        proposal_id="proposal-7",
        effect_type="bulletin.publish",
        effect_version=1,
        payload_digest=digest_payload({"message": "ready"} if payload is None else payload),
        target=TargetIdentity("bulletin", "release-notes"),
        requested_authority_class="bulletin.publish",
    )


def _fence(proposal: EffectProposal) -> EffectFence:
    return EffectFence(
        proposal_id=proposal.proposal_id,
        proposal_digest=proposal.digest,
        authority_epoch=4,
        target_head="revision-11",
        episode_id="episode-3",
        attachment_id="attachment-8",
        attachment_epoch=2,
    )


def _receipt(proposal: EffectProposal, raw_evidence: object | None = None) -> EffectReceipt:
    return EffectReceipt(
        proposal_id=proposal.proposal_id,
        proposal_digest=proposal.digest,
        payload_digest=proposal.payload_digest,
        target=proposal.target,
        receipt_digest=digest_payload({"provider_record": "record-1"} if raw_evidence is None else raw_evidence),
    )


class _Fences:
    def __init__(self, current: EffectFence):
        self.value = current
        self.calls = 0

    def current(self, proposal: EffectProposal) -> EffectFence:
        self.calls += 1
        return self.value


class _ScriptedAdapter:
    def __init__(self, lookups: list[LookupResult | Exception], executions: list[EffectReceipt | Exception]):
        self.lookups = lookups
        self.executions = executions
        self.lookup_calls = 0
        self.execute_calls = 0

    def lookup(self, proposal: EffectProposal) -> LookupResult:
        value = self.lookups[self.lookup_calls]
        self.lookup_calls += 1
        if isinstance(value, Exception):
            raise value
        return value

    def execute(self, proposal: EffectProposal, payload: dict[str, object], fence: EffectFence) -> EffectReceipt:
        value = self.executions[self.execute_calls]
        self.execute_calls += 1
        if isinstance(value, Exception):
            raise value
        return value


def test_proposal_and_fence_round_trip_as_exact_versioned_secret_free_data() -> None:
    secret = "SECRET-canary-not-for-evidence"
    payload = {"message": "ready", "credential": secret, "labels": ["release", "green"]}
    proposal = _proposal(payload)
    fence = _fence(proposal)

    assert proposal.to_data() == {
        "schema_version": 1,
        "proposal_id": "proposal-7",
        "effect_type": "bulletin.publish",
        "effect_version": 1,
        "payload_digest": proposal.payload_digest,
        "target": {"target_type": "bulletin", "target_id": "release-notes"},
        "requested_authority_class": "bulletin.publish",
    }
    assert EffectProposal.from_data(proposal.to_data()) == proposal
    assert EffectFence.from_data(fence.to_data()) == fence
    assert proposal.digest.startswith("sha256:")
    assert secret not in json.dumps(proposal.to_data())
    assert secret not in repr(proposal)


_JSON = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=30),
    lambda children: st.lists(children, max_size=5) | st.dictionaries(st.text(max_size=12), children, max_size=5),
    max_leaves=20,
)


@settings(max_examples=60)
@given(st.dictionaries(st.text(max_size=12), _JSON, max_size=8))
def test_payload_digest_is_a_canonical_replay_identity(payload: dict[str, object]) -> None:
    reordered = dict(reversed(tuple(payload.items())))
    replayed = json.loads(json.dumps(payload, ensure_ascii=False))

    assert digest_payload(payload) == digest_payload(reordered) == digest_payload(replayed)
    assert _proposal(payload).digest == EffectProposal.from_data(_proposal(payload).to_data()).digest


@pytest.mark.parametrize(
    "payload",
    (
        ["not-an-object"],
        {"tuple": (1, 2)},
        {"float": 1.25},
        {1: "non-string-key"},
    ),
)
def test_payload_digest_rejects_non_strict_json_without_echoing_payload(payload: object) -> None:
    with pytest.raises((TypeError, ValueError)) as error:
        digest_payload(payload)
    assert "not-an-object" not in str(error.value)
    assert "non-string-key" not in str(error.value)


@pytest.mark.parametrize(
    "mutation",
    (
        lambda data: data | {"raw_payload": {"secret": "forbidden"}},
        lambda data: data | {"schema_version": 2},
        lambda data: data | {"effect_version": True},
        lambda data: data | {"payload_digest": "not-a-digest"},
        lambda data: data | {"target": data["target"] | {"provider": "github"}},
    ),
)
def test_proposal_decoder_rejects_unknown_ambiguous_and_noncanonical_data(mutation) -> None:
    data = _proposal().to_data()
    with pytest.raises((TypeError, ValueError)):
        EffectProposal.from_data(mutation(data))


def test_reject_and_approve_are_exactly_correlated_and_structurally_distinct() -> None:
    proposal = _proposal()
    fence = _fence(proposal)
    rejected = EffectDecision.reject(proposal, "host-policy-denied")
    approved = EffectDecision.approve(proposal, fence)

    assert rejected.kind is EffectDecisionKind.REJECT and rejected.reason_code == "host-policy-denied"
    assert approved.kind is EffectDecisionKind.APPROVE and approved.fence == fence
    assert EffectDecision.from_data(rejected.to_data()) == rejected
    assert EffectDecision.from_data(approved.to_data()) == approved
    with pytest.raises(ValueError, match="proposal"):
        EffectDecision.approve(proposal, replace(fence, proposal_id="another-proposal"))


def test_receipt_lookup_evidence_and_decision_serialization_are_strict() -> None:
    proposal = _proposal()
    fence = _fence(proposal)
    receipt = _receipt(proposal)
    lookup = LookupResult.applied(receipt)
    evidence = EffectEvidence(
        proposal.proposal_id,
        proposal.digest,
        proposal.payload_digest,
        proposal.target,
        fence,
        LookupDisposition.APPLIED,
        receipt.receipt_digest,
    )
    decision = EffectDecision(
        EffectDecisionKind.ALREADY_APPLIED,
        proposal.proposal_id,
        proposal.digest,
        fence=fence,
        evidence=evidence,
    )

    for value in (receipt, lookup, evidence, decision):
        assert type(value).from_data(value.to_data()) == value
    with pytest.raises(ValueError):
        LookupResult(LookupDisposition.APPLIED)
    with pytest.raises(ValueError):
        LookupResult(LookupDisposition.SAFE_TO_RETRY, receipt)
    with pytest.raises(ValueError, match="evidence fence"):
        replace(evidence, fence=replace(fence, proposal_id="another-proposal"))


def test_gateway_rejects_payload_or_approval_mismatch_before_provider_lookup() -> None:
    proposal = _proposal()
    fence = _fence(proposal)
    adapter = _ScriptedAdapter([LookupResult.safe_to_retry()], [_receipt(proposal)])
    gateway = EffectGateway(adapter, _Fences(fence))

    with pytest.raises(ValueError, match="payload digest"):
        gateway.execute(proposal, {"message": "changed"}, EffectDecision.approve(proposal, fence))
    with pytest.raises(TypeError, match="approved"):
        gateway.execute(proposal, {"message": "ready"}, EffectDecision.reject(proposal, "denied"))
    assert adapter.lookup_calls == adapter.execute_calls == 0


def test_gateway_never_blind_retries_an_uncertain_response_and_reports_safe_recovery() -> None:
    secret = "SECRET-provider-exception-canary"
    proposal = _proposal()
    fence = _fence(proposal)
    adapter = _ScriptedAdapter(
        [LookupResult.safe_to_retry(), LookupResult.safe_to_retry()],
        [RuntimeError(secret)],
    )
    decision = EffectGateway(adapter, _Fences(fence)).execute(
        proposal,
        {"message": "ready"},
        EffectDecision.approve(proposal, fence),
    )

    assert decision.kind is EffectDecisionKind.INDETERMINATE
    assert decision.evidence is not None and decision.evidence.recovery is LookupDisposition.SAFE_TO_RETRY
    assert adapter.lookup_calls == 2 and adapter.execute_calls == 1
    assert secret not in repr(decision)
    assert secret not in json.dumps(decision.to_data())


def test_uncertain_response_is_reconciled_as_already_applied_with_exact_receipt() -> None:
    proposal = _proposal()
    fence = _fence(proposal)
    receipt = _receipt(proposal)
    adapter = _ScriptedAdapter(
        [LookupResult.safe_to_retry(), LookupResult.applied(receipt)],
        [TimeoutError("response lost")],
    )
    decision = EffectGateway(adapter, _Fences(fence)).execute(
        proposal,
        {"message": "ready"},
        EffectDecision.approve(proposal, fence),
    )

    assert decision.kind is EffectDecisionKind.ALREADY_APPLIED
    assert decision.evidence is not None and decision.evidence.receipt_digest == receipt.receipt_digest
    assert adapter.execute_calls == 1


@pytest.mark.parametrize(
    ("lookup", "kind"),
    (
        (LookupResult.superseded(), EffectDecisionKind.SUPERSEDED),
        (LookupResult.indeterminate(), EffectDecisionKind.INDETERMINATE),
    ),
)
def test_lookup_dispositions_stop_before_fences_or_execution(lookup: LookupResult, kind: EffectDecisionKind) -> None:
    proposal = _proposal()
    fences = _Fences(_fence(proposal))
    adapter = _ScriptedAdapter([lookup], [])
    decision = EffectGateway(adapter, fences).execute(
        proposal,
        {"message": "ready"},
        EffectDecision.approve(proposal, _fence(proposal)),
    )

    assert decision.kind is kind
    assert fences.calls == adapter.execute_calls == 0


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("authority_epoch", 5),
        ("target_head", "revision-12"),
        ("proposal_digest", "sha256:" + "0" * 64),
        ("episode_id", "episode-4"),
        ("attachment_id", "attachment-9"),
        ("attachment_epoch", 3),
    ),
)
def test_each_fence_is_refreshed_after_lookup_and_stale_state_never_executes(field: str, value: object) -> None:
    proposal = _proposal()
    expected = _fence(proposal)
    fences = _Fences(replace(expected, **{field: value}))
    adapter = _ScriptedAdapter([LookupResult.safe_to_retry()], [])
    decision = EffectGateway(adapter, fences).execute(
        proposal,
        {"message": "ready"},
        EffectDecision.approve(proposal, expected),
    )

    assert decision.kind is EffectDecisionKind.SUPERSEDED
    assert decision.evidence is not None and decision.evidence.recovery is LookupDisposition.SUPERSEDED
    assert adapter.lookup_calls == fences.calls == 1
    assert adapter.execute_calls == 0


def test_uncorrelated_receipt_is_indeterminate_never_misreported_as_success() -> None:
    proposal = _proposal()
    fence = _fence(proposal)
    wrong = replace(_receipt(proposal), proposal_id="another-proposal")
    adapter = _ScriptedAdapter([LookupResult.safe_to_retry(), LookupResult.safe_to_retry()], [wrong])
    decision = EffectGateway(adapter, _Fences(fence)).execute(
        proposal,
        {"message": "ready"},
        EffectDecision.approve(proposal, fence),
    )

    assert decision.kind is EffectDecisionKind.INDETERMINATE
    assert decision.proposal_id == proposal.proposal_id
    assert decision.evidence is not None
    assert decision.evidence.proposal_id == proposal.proposal_id
    assert decision.evidence.recovery is LookupDisposition.SAFE_TO_RETRY
    assert decision.evidence.receipt_digest is None
    assert adapter.lookup_calls == 2 and adapter.execute_calls == 1


@pytest.mark.parametrize(
    "lookup",
    (
        RuntimeError("SECRET-lookup-crash"),
        LookupResult.applied(replace(_receipt(_proposal()), proposal_id="another-proposal")),
    ),
)
def test_lookup_crash_or_uncorrelated_lookup_evidence_is_indeterminate_and_never_executes(
    lookup: LookupResult | Exception,
) -> None:
    proposal = _proposal()
    fence = _fence(proposal)
    adapter = _ScriptedAdapter([lookup], [])
    fences = _Fences(fence)
    decision = EffectGateway(adapter, fences).execute(
        proposal,
        {"message": "ready"},
        EffectDecision.approve(proposal, fence),
    )

    assert decision.kind is EffectDecisionKind.INDETERMINATE
    assert decision.evidence is not None and decision.evidence.recovery is LookupDisposition.INDETERMINATE
    assert adapter.lookup_calls == 1 and adapter.execute_calls == 0
    assert fences.calls == 0
    assert "SECRET" not in json.dumps(decision.to_data())


@pytest.mark.parametrize(
    ("failure", "kind", "recovery"),
    (
        ("raise", EffectDecisionKind.INDETERMINATE, LookupDisposition.SAFE_TO_RETRY),
        ("wrong-type", EffectDecisionKind.INDETERMINATE, LookupDisposition.SAFE_TO_RETRY),
        ("wrong-proposal", EffectDecisionKind.SUPERSEDED, LookupDisposition.SUPERSEDED),
    ),
)
def test_fence_source_crash_malformed_answer_or_stale_proposal_remains_fail_closed(
    failure: str,
    kind: EffectDecisionKind,
    recovery: LookupDisposition,
) -> None:
    proposal = _proposal()
    fence = _fence(proposal)

    class BrokenFences:
        def current(self, candidate: EffectProposal) -> object:
            if failure == "raise":
                raise RuntimeError("SECRET-fence-crash")
            if failure == "wrong-type":
                return "not-a-fence"
            return replace(fence, proposal_id="another-proposal")

    adapter = _ScriptedAdapter([LookupResult.safe_to_retry()], [])
    decision = EffectGateway(adapter, BrokenFences()).execute(
        proposal,
        {"message": "ready"},
        EffectDecision.approve(proposal, fence),
    )

    assert decision.kind is kind
    assert decision.evidence is not None and decision.evidence.recovery is recovery
    assert adapter.lookup_calls == 1 and adapter.execute_calls == 0
    assert "SECRET" not in json.dumps(decision.to_data())


def test_adapter_exceptions_and_raw_provider_evidence_are_digest_only() -> None:
    secret = "SECRET-raw-provider-canary"
    proposal = _proposal()
    fence = _fence(proposal)
    receipt = _receipt(proposal, {"raw": secret})
    adapter = _ScriptedAdapter([LookupResult.safe_to_retry()], [receipt])
    decision = EffectGateway(adapter, _Fences(fence)).execute(
        proposal,
        {"message": "ready"},
        EffectDecision.approve(proposal, fence),
    )

    assert decision.kind is EffectDecisionKind.EXECUTE
    assert secret not in repr(decision)
    assert secret not in json.dumps(decision.to_data())
