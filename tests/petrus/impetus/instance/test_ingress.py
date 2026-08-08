"""
Behavioral tests for ingress: external delivery to source transitions.

A source transition (no input arcs) never fires from the scheduler; it fires
only when the runtime delivers an external event to it [DR 2026-07-08
source-transition-ingress]. Delivery hands the kernel token(s): they enter the
firing as the binding's tokens, and the ruled no-symbol -> passthrough default
color-routes them through the output arcs — runtime injection IS passthrough
over the delivered tokens (Navigator ruling, slice 8). A declared handler
receives the same binding and may transform. The event is recorded before the
firing it initiates, so replay re-applies recorded movements and never
re-delivers.
"""

from __future__ import annotations

# Pip imports
import pytest

# Internal imports
from petrus.impetus.history import (
    InstanceCreated,
    ExternalEventDelivered,
    FiringBegun,
    FiringCompleted,
    FiringFailed,
    DeliveryRegistrationOpened,
    TokensProduced,
    replay_accepted_identities,
    replay_marking,
)
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.instance import Instance, PriorAcknowledgement
from petrus.impetus.petrinet import Arc, Net, NetPath, Place, Transition

PAYMENT = Token("Payment", {"amount": 150, "currency": "USD"})
SIGNAL = Token("Signal", {"kind": "cancel"})


class TestDelivery:
    """One general source transition demultiplexing mixed events by color."""

    PAYMENTS, SIGNALS, INGEST = NetPath("payments"), NetPath("signals"), NetPath("ingest")

    def net(self) -> Net:
        return Net(
            places=[Place(self.PAYMENTS), Place(self.SIGNALS)],
            transitions=[Transition(self.INGEST)],
            arcs=[
                Arc(self.INGEST, self.PAYMENTS, color="Payment"),
                Arc(self.INGEST, self.SIGNALS, color="Signal"),
            ],
        )

    def test_delivered_tokens_route_by_color_through_the_output_arcs(self):
        # The DR's demultiplex-for-free consequence: one delivery, mixed
        # tokens, each landing where its color contract admits it — and the
        # recorded event fact carries every delivered token.
        instance = Instance(self.net())
        instance.deliver(self.INGEST, (PAYMENT, SIGNAL))
        assert instance.marking == Marking({self.PAYMENTS: (PAYMENT,), self.SIGNALS: (SIGNAL,)})
        assert (
            ExternalEventDelivered(self.INGEST, (PAYMENT, SIGNAL), identity="occurrence-1", occurrence=1)
            in instance.history.records
        )

    def test_a_single_token_needs_no_sequence(self):
        instance = Instance(self.net())
        instance.deliver(self.INGEST, PAYMENT)
        assert instance.marking == Marking({self.PAYMENTS: (PAYMENT,)})

    def test_delivery_records_the_event_then_the_firing_lifecycle(self):
        # The external event is a recorded fact BEFORE the firing it initiates;
        # the firing carries no selection record (the scheduler never chose)
        # and no consume records (a source consumes nothing).
        instance = Instance(self.net())
        instance.deliver(self.INGEST, PAYMENT)
        assert instance.history.records == (
            InstanceCreated(instance.instance_id),
            DeliveryRegistrationOpened(self.INGEST, "default", occurrence=None),
            ExternalEventDelivered(self.INGEST, (PAYMENT,), identity="occurrence-1", occurrence=1),
            FiringBegun(self.INGEST, occurrence=1),
            TokensProduced(self.PAYMENTS, (PAYMENT,), occurrence=1),
            FiringCompleted(self.INGEST, occurrence=1),
        )

    def test_the_firing_reports_nothing_consumed(self):
        instance = Instance(self.net())
        firing = instance.deliver(self.INGEST, PAYMENT)
        assert firing.transition == self.INGEST
        assert firing.consumed == ()
        assert firing.produced == ((self.PAYMENTS, PAYMENT),)

    def test_replay_reapplies_the_recorded_movements(self):
        instance = Instance(self.net())
        instance.deliver(self.INGEST, (PAYMENT, SIGNAL))
        assert replay_marking(instance.history) == instance.marking

    def test_delivered_tokens_no_arc_admits_are_leftover(self):
        # Permissive flow: an unadmitted delivered token is simply not
        # deposited — allowed, not an error [DR permissive-flow-defaults].
        instance = Instance(self.net())
        firing = instance.deliver(self.INGEST, Token("Unknown", {"x": 1}))
        assert firing.produced == ()
        assert instance.marking == Marking()
        assert not [r for r in instance.history if isinstance(r, TokensProduced)]

    def test_a_supplied_delivery_identity_is_recorded(self):
        # The ingress adapter extracts or constructs a stable delivery
        # identity (a webhook's provider event id); the recorded fact carries
        # it [DR 2026-07-14 source-delivery-projection-and-identity].
        # Idempotent acceptance by that identity is the door's
        # (TestDeliveryIdentityEnforcement below).
        instance = Instance(self.net())
        instance.deliver(self.INGEST, PAYMENT, identity="evt_123")
        assert (
            ExternalEventDelivered(self.INGEST, (PAYMENT,), identity="evt_123", occurrence=1)
            in instance.history.records
        )

    def test_an_unsupplied_identity_derives_from_the_occurrence(self):
        # No external identity supplied: the writer derives a self-identity
        # from the occurrence id it mints — stable across replay, distinct
        # per delivery, and honest that no transport identity existed.
        instance = Instance(self.net())
        instance.deliver(self.INGEST, PAYMENT)
        instance.deliver(self.INGEST, SIGNAL)
        identities = [r.identity for r in instance.history.records if isinstance(r, ExternalEventDelivered)]
        assert identities == ["occurrence-1", "occurrence-2"]

    def test_a_supplied_identity_in_the_writer_reserved_namespace_is_rejected(self):
        # "occurrence-" is the derived self-identity's namespace: a supplied
        # "occurrence-2" would collide with a later derived one, and DS2's
        # dedup would collapse two distinct events into one. Refused at the
        # door, before anything is recorded, naming the reserved prefix.
        instance = Instance(self.net())
        with pytest.raises(ValueError, match=r"identity 'occurrence-2' uses the writer-reserved 'occurrence-' prefix"):
            instance.deliver(self.INGEST, PAYMENT, identity="occurrence-2")
        assert not [r for r in instance.history if isinstance(r, ExternalEventDelivered)]

    def test_an_empty_identity_is_rejected_before_recording(self):
        # The ingress seam validates before it records [convention 28]: an
        # empty identity can never tell deliveries apart, so it is a caller
        # bug, not a fact.
        instance = Instance(self.net())
        with pytest.raises(ValueError, match=r"delivery to ingest: identity must be a non-empty string"):
            instance.deliver(self.INGEST, PAYMENT, identity="")
        assert not [r for r in instance.history if isinstance(r, ExternalEventDelivered)]

    def test_delivery_to_a_non_source_transition_is_rejected(self):
        # The rejection names the transition and why it cannot take delivery.
        a, t = NetPath("a"), NetPath("t")
        net = Net(places=[Place(a)], transitions=[Transition(t)], arcs=[Arc(a, t)])
        instance = Instance(net, Marking({a: (Token.black(),)}))
        with pytest.raises(ValueError, match=r"cannot deliver to transition t: it has input arcs"):
            instance.deliver(t, PAYMENT)

    def test_delivery_to_an_unknown_transition_is_rejected(self):
        instance = Instance(self.net())
        with pytest.raises(ValueError, match=r"cannot deliver to nowhere: not a transition"):
            instance.deliver("nowhere", PAYMENT)

    def test_an_empty_delivery_is_rejected(self):
        # An external event carries at least one token; delivering nothing is
        # a caller bug, not a fact worth recording.
        instance = Instance(self.net())
        with pytest.raises(ValueError, match=r"delivery to ingest requires at least one token"):
            instance.deliver(self.INGEST, ())

    def test_a_non_token_delivery_is_rejected_before_recording(self):
        # This is the seam where outside-world data enters the kernel, and a
        # str is a Sequence — without the element check, deliver("...", "oops")
        # would record and route four character "tokens". Rejected before the
        # event fact is recorded (Navigator ruling, slice-8 review).
        instance = Instance(self.net())
        with pytest.raises(ValueError, match=r"delivery to ingest: every delivered item must be a Token"):
            instance.deliver(self.INGEST, "oops")
        assert not [r for r in instance.history if isinstance(r, ExternalEventDelivered)]


class TestDeliveryIdentityEnforcement:
    """
    Idempotent acceptance by stable delivery identity, enforced at the single
    writer [DR 2026-07-14 source-delivery-projection-and-identity]: the same
    delivery identity is accepted once — a redelivery returns the prior
    acknowledgement with no second semantic record or token — while distinct
    identities are preserved even when their data is equal. The identity
    check precedes every other door validation, registration armed-ness
    included: a one-shot registration may have closed after the first commit,
    and the broker retry still needs its acknowledgement. Duplicate attempts
    are operational telemetry, never canonical history.
    """

    SRC, OUT = NetPath("src"), NetPath("out")

    def net(self) -> Net:
        return Net(places=[Place(self.OUT)], transitions=[Transition(self.SRC)], arcs=[Arc(self.SRC, self.OUT)])

    def test_a_redelivered_identity_returns_the_prior_acknowledgement_without_an_append(self):
        instance = Instance(self.net())
        first = instance.deliver(self.SRC, PAYMENT, identity="evt_123")
        before = instance.history.records

        acknowledgement = instance.deliver(self.SRC, PAYMENT, identity="evt_123")

        assert acknowledgement == PriorAcknowledgement("evt_123", first.occurrence)
        assert instance.history.records == before
        assert instance.marking == Marking({self.OUT: (PAYMENT,)})

    def test_the_identity_check_precedes_registration_validation(self):
        # The ruled ordering [DR 2026-07-14]: the source sealed after the
        # first commit, and the broker retry is still acknowledged — never
        # told "no armed delivery registration".
        instance = Instance(self.net())
        first = instance.deliver(self.SRC, PAYMENT, identity="evt_123")
        instance.seal(self.SRC)

        acknowledgement = instance.deliver(self.SRC, PAYMENT, identity="evt_123")

        assert acknowledgement == PriorAcknowledgement("evt_123", first.occurrence)
        # A NEW identity still meets the sealed door: the registration check
        # holds for everything that is not a redelivery.
        with pytest.raises(ValueError, match="no armed delivery registration"):
            instance.deliver(self.SRC, PAYMENT, identity="evt_124")

    def test_reusing_an_identity_for_changed_content_or_source_is_a_conflict(self):
        # Exact transport redelivery is idempotent; an identity naming another
        # fact is not a retry. The recorded delivery supplies enough evidence
        # to refuse both payload and address drift before current door state.
        other = NetPath("other")
        net = Net(
            places=[Place(self.OUT)],
            transitions=[Transition(self.SRC), Transition(other)],
            arcs=[Arc(self.SRC, self.OUT), Arc(other, self.OUT)],
        )
        instance = Instance(net)
        instance.deliver(self.SRC, PAYMENT, identity="evt_123")
        before = instance.history.records

        with pytest.raises(ValueError, match="identity conflict.*different delivery content"):
            instance.deliver(self.SRC, Token("Payment", {"amount": 8}), identity="evt_123")
        with pytest.raises(ValueError, match="identity conflict.*source src"):
            instance.deliver(other, PAYMENT, identity="evt_123")

        assert instance.history.records == before

    def test_distinct_identities_with_equal_data_are_both_preserved(self):
        # Distinct business events carrying equal data are two facts; only
        # transport redelivery collapses [DR 2026-07-14].
        instance = Instance(self.net())
        instance.deliver(self.SRC, PAYMENT, identity="evt_1")
        instance.deliver(self.SRC, PAYMENT, identity="evt_2")

        events = [r for r in instance.history if isinstance(r, ExternalEventDelivered)]
        assert [e.identity for e in events] == ["evt_1", "evt_2"]
        assert instance.marking == Marking({self.OUT: (PAYMENT, PAYMENT)})

    def test_derived_self_identities_never_collapse_distinct_deliveries(self):
        # No supplied identity: each delivery derives its own occurrence
        # self-identity, honest that no transport identity existed — equal
        # data alone never dedups.
        instance = Instance(self.net())
        instance.deliver(self.SRC, PAYMENT)
        instance.deliver(self.SRC, PAYMENT)

        assert instance.marking == Marking({self.OUT: (PAYMENT, PAYMENT)})

    def test_an_identity_is_accepted_even_when_the_source_projection_fails(self):
        # The event fact is recorded before the firing it initiates, and the
        # identity is accepted the moment that fact commits: a raising
        # source projection propagates, but the broker retry of the SAME
        # identity is still answered with the prior acknowledgement — the
        # record answers it, exactly as replay would.
        def explode(binding, outputs):
            raise RuntimeError("projection bug")

        net = Net(
            places=[Place(self.OUT)],
            transitions=[Transition(self.SRC, handler="explode")],
            arcs=[Arc(self.SRC, self.OUT)],
        )
        instance = Instance(net, handlers={"explode": explode})

        with pytest.raises(RuntimeError, match="projection bug"):
            instance.deliver(self.SRC, PAYMENT, identity="evt_123")

        acknowledgement = instance.deliver(self.SRC, PAYMENT, identity="evt_123")

        assert acknowledgement == PriorAcknowledgement("evt_123", 1)
        events = [r for r in instance.history if isinstance(r, ExternalEventDelivered)]
        assert [e.identity for e in events] == ["evt_123"]

    def test_the_accepted_identity_index_rebuilds_at_resume(self, tmp_path):
        # The index is a projection of the ExternalEventDelivered records —
        # live and rebuilt: a redelivery after the crash is acknowledged
        # against the recorded acceptance.
        path = tmp_path / "history.jsonl"
        instance = Instance(self.net(), history=JsonlHistoryStore(path))
        first = instance.deliver(self.SRC, PAYMENT, identity="evt_123")
        del instance  # the kill

        resumed = Instance.resume(self.net(), JsonlHistoryStore(path))
        before = resumed.history.records

        acknowledgement = resumed.deliver(self.SRC, PAYMENT, identity="evt_123")

        assert acknowledgement == PriorAcknowledgement("evt_123", first.occurrence)
        assert resumed.history.records == before

        with pytest.raises(ValueError, match="identity conflict"):
            resumed.deliver(self.SRC, Token("Payment", {"amount": 8}), identity="evt_123")
        assert resumed.history.records == before

    def test_a_trace_with_a_twice_accepted_identity_is_replay_divergence(self):
        # The live writer accepts an identity once, so a trace that disagrees
        # is corrupted — a rebuilt index is valid only if the live writer
        # could have written it [convention 48].
        history = InMemoryHistoryStore()
        history.extend(
            [
                ExternalEventDelivered(self.SRC, (PAYMENT,), identity="evt_1", occurrence=1),
                ExternalEventDelivered(self.SRC, (PAYMENT,), identity="evt_1", occurrence=2),
            ]
        )
        with pytest.raises(ValueError, match="replay divergence.*evt_1.*accepted twice"):
            replay_accepted_identities(history)


class TestHandledSource:
    """A source transition with a declared handler transforms the delivered tokens."""

    RECEIPTS, INGEST = NetPath("receipts"), NetPath("ingest")
    RAW = Token("RawEvent", {"body": '{"total": 3}'})
    RECEIPT = Token("Receipt", {"total": 3})

    def net(self) -> Net:
        return Net(
            places=[Place(self.RECEIPTS)],
            transitions=[Transition(self.INGEST, handler="parse")],
            arcs=[Arc(self.INGEST, self.RECEIPTS, color="Receipt")],
        )

    def test_the_handler_receives_the_delivered_tokens_as_the_binding(self):
        seen = []

        def parse(binding, outputs):
            seen.append(binding.tokens)
            return {self.RECEIPTS: (self.RECEIPT,)}

        instance = Instance(self.net(), handlers={"parse": parse})
        instance.deliver(self.INGEST, self.RAW)
        assert seen == [(self.RAW,)]
        assert instance.marking == Marking({self.RECEIPTS: (self.RECEIPT,)})

    def test_a_handled_delivery_records_the_lifecycle_of_a_local_projection(self):
        # The ruled per-delivery record sequence — event fact, then begin ->
        # produce -> complete, no selection, no consume — holds on the handler
        # path: a source handler is a local, atomic, deterministic projection
        # [DR 2026-07-14 source-delivery-projection-and-identity], so no
        # activity records appear between the movements.
        instance = Instance(self.net(), handlers={"parse": lambda b, outputs: {self.RECEIPTS: (self.RECEIPT,)}})
        instance.deliver(self.INGEST, self.RAW)
        assert instance.history.records == (
            InstanceCreated(instance.instance_id),
            DeliveryRegistrationOpened(self.INGEST, "default", occurrence=None),
            ExternalEventDelivered(self.INGEST, (self.RAW,), identity="occurrence-1", occurrence=1),
            FiringBegun(self.INGEST, occurrence=1),
            TokensProduced(self.RECEIPTS, (self.RECEIPT,), occurrence=1),
            FiringCompleted(self.INGEST, occurrence=1),
        )

    def test_the_handler_result_is_recorded_and_never_rerun(self):
        # Replay re-applies the recorded produced tokens; the handler ran once.
        calls = []

        def parse(binding, outputs):
            calls.append(binding.transition)
            return {self.RECEIPTS: (self.RECEIPT,)}

        instance = Instance(self.net(), handlers={"parse": parse})
        instance.deliver(self.INGEST, self.RAW)
        assert replay_marking(instance.history) == instance.marking
        assert calls == [self.INGEST]

    def test_the_event_is_recorded_before_a_raising_handler_propagates(self):
        # Recording precedes and is independent of consumption: the event fact
        # survives the failed firing — which now ends as a recorded terminal
        # failure, not a vanished occurrence; the marking does not move.
        def parse(binding, outputs):
            raise RuntimeError("boom")

        instance = Instance(self.net(), handlers={"parse": parse})
        with pytest.raises(RuntimeError, match="boom"):
            instance.deliver(self.INGEST, self.RAW)
        assert (
            ExternalEventDelivered(self.INGEST, (self.RAW,), identity="occurrence-1", occurrence=1)
            in instance.history.records
        )
        assert isinstance(instance.history.records[-1], FiringFailed)
        assert instance.marking == Marking()
