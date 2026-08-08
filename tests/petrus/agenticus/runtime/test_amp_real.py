"""Opt-in live acceptance for the exact Amp A1 provider-managed Orb lane."""

from __future__ import annotations

import os
import secrets
import time

import pytest

from petrus.agenticus.attachment.episode import EpisodeAttachment
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorIdentity, DescriptorKind
from petrus.agenticus.catalog.resolution import ResolutionSnapshot
from petrus.agenticus.connection.custody import ConnectionIdentity, ConnectionStatus, ConnectionView
from petrus.agenticus.runtime.amp import (
    AMP_CONNECTION_CAPABILITIES,
    AMP_CONTINUATION_CAPABILITIES,
    AMP_CONTINUATION_DESCRIPTOR,
    AMP_PROGRAM_CAPABILITIES,
    AMP_PROVIDER_MANAGED_HANDS,
    AMP_PROVIDER_MANAGED_TERRITORY,
    AmpContinuationCodec,
    AmpContinuationPayloadV1,
    AmpProviderManagedBinding,
    AmpRuntimeAdapter,
    AmpRuntimeConfig,
    AmpRuntimeInvocation,
)
from petrus.agenticus.runtime.installation import ProbeDisposition
from petrus.agenticus.runtime.profiles import AMP_A1
from petrus.agenticus.thread.continuation import Continuation, ContinuationState
from petrus.agenticus.thread.identity import ContinuationId, EpisodeId, ThreadId, TurnId
from petrus.agenticus.thread.lifecycle import TurnOutcome

HOST_FENCED_EFFECT = CapabilityDescriptor(
    DescriptorIdentity(DescriptorKind.EFFECT, "host.fenced", 1),
    frozenset({"effect.host-fenced"}),
)


class Continuations:
    def __init__(self) -> None:
        self.values: dict[str, AmpContinuationPayloadV1] = {}

    def store(self, operation_id: str, payload: AmpContinuationPayloadV1) -> str:
        reference = f"live-amp-continuation-{operation_id}"
        current = self.values.get(reference)
        if current is not None and current != payload:
            raise RuntimeError("live Amp Continuation custody conflict")
        self.values[reference] = payload
        return reference

    def load(self, state_reference: str) -> AmpContinuationPayloadV1:
        return self.values[state_reference]


class Turns:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, str]] = {}

    def store_turn(self, operation_id: str, thread_id: str, final_text: str) -> str:
        reference = f"live-amp-turn-{operation_id}"
        current = self.values.get(reference)
        value = (thread_id, final_text)
        if current is not None and current != value:
            raise RuntimeError("live Amp Turn custody conflict")
        self.values[reference] = value
        return reference


def _connection() -> ConnectionView:
    return ConnectionView(
        ConnectionIdentity("live-amp-platform", "amp", "installation-account", "platform-managed"),
        ConnectionStatus.READY,
        1,
        1,
        None,
    )


def _attachment(episode: EpisodeId) -> EpisodeAttachment:
    snapshot = ResolutionSnapshot(
        1,
        (
            AMP_A1,
            AMP_CONNECTION_CAPABILITIES,
            AMP_PROGRAM_CAPABILITIES,
            AMP_PROVIDER_MANAGED_HANDS,
            AMP_PROVIDER_MANAGED_TERRITORY,
            AMP_CONTINUATION_CAPABILITIES,
            HOST_FENCED_EFFECT,
        ),
    )
    return EpisodeAttachment(
        episode_id=episode,
        snapshot=snapshot,
        binding=AmpProviderManagedBinding(),
        attachment_id=f"attachment-{episode.value}",
        deadline=time.monotonic() + 150,
    )


@pytest.mark.real_provider_acceptance
@pytest.mark.skipif(
    os.environ.get("PETRUS_RUN_CV16_AMP_A1") != "1",
    reason="set PETRUS_RUN_CV16_AMP_A1=1 to run the authenticated Amp A1 cell",
)
def test_amp_a1_new_and_continue_in_provider_managed_orb() -> None:
    project = os.environ.get("PETRUS_AMP_PROJECT", "henriquebastos/petrus")
    marker_one = f"CV16_A1_{secrets.token_hex(8).upper()}"
    marker_two = f"CV16_A1_{secrets.token_hex(8).upper()}"
    continuations = Continuations()
    turns = Turns()
    adapter = AmpRuntimeAdapter(
        AmpRuntimeConfig(project, mode="low", visibility="private", no_archive_after_execute=False),
        AmpContinuationCodec(continuations),
        turns,
    )
    probe = adapter.probe()
    assert probe.disposition is ProbeDisposition.READY

    episode_one = EpisodeId("live-amp-episode-1")
    attachment_one = _attachment(episode_one)
    first_operation = adapter.start(
        AmpRuntimeInvocation(
            "live-amp-operation-1",
            episode_one,
            TurnId("live-amp-turn-1"),
            f"Reply exactly {marker_one}. Do not call tools or modify files.",
            _connection(),
            attachment_one,
        )
    )
    first = first_operation.wait(150)
    assert first.outcome is TurnOutcome.COMPLETED and first.accepted_appends == 1
    assert turns.values[first.output_reference or ""][1].strip() == marker_one
    first_payload = continuations.values[first.continuation_reference or ""]
    assert first_payload.thread_id.startswith("T-")
    assert attachment_one.settle().settlement.verified

    episode_two = EpisodeId("live-amp-episode-2")
    attachment_two = _attachment(episode_two)
    claimed = Continuation(
        ContinuationId("live-amp-continuation-1"),
        ThreadId("live-agenticus-thread"),
        AMP_CONTINUATION_DESCRIPTOR,
        first.continuation_reference or "",
        ContinuationState.IN_USE,
    )
    second_operation = adapter.start(
        AmpRuntimeInvocation(
            "live-amp-operation-2",
            episode_two,
            TurnId("live-amp-turn-2"),
            f"Remember the exact prior marker. Reply exactly {marker_one}|{marker_two}. Do not call tools or modify files.",
            _connection(),
            attachment_two,
            claimed,
        )
    )
    second = second_operation.wait(150)

    assert second.outcome is TurnOutcome.COMPLETED and second.accepted_appends == 1
    assert turns.values[second.output_reference or ""][1].strip() == f"{marker_one}|{marker_two}"
    second_payload = continuations.values[second.continuation_reference or ""]
    assert second_payload.thread_id == first_payload.thread_id
    assert attachment_two.settle().settlement.verified
