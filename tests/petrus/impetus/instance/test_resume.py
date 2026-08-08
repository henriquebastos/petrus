"""
Behavioral tests for resume: rebuilding a live Instance from its records.

The event history is the whole truth of an instance, so a crash loses nothing
the records hold: ``Instance.resume`` computes every piece of live state as
the projection the records are the authority of — the marking
(``replay_marking``), the armed registrations (``replay_armed``), the clock
watermark (the last record's instant), the occurrence counter (no recorded id
ever re-mints), and the in-flight occurrences (``replay_in_flight``), rebuilt as
real ``FiringOccurrence`` values a driver can ``complete()`` or ``fail()``. The
caller re-supplies what records never hold — the net and its bound
implementations: callables are code, not facts. Closes the marking-only-resume
gap of debt 2026-07-10T0600Z (part 3).
"""

from __future__ import annotations

# Pip imports
import pytest

# Internal imports
from petrus.impetus.binding import HandlerResult
from petrus.impetus.instance.firing import replay_in_flight
from petrus.impetus.history import (
    CandidateSelected,
    ExternalEventDelivered,
    FiringBegun,
    FiringCompleted,
    FiringFailed,
    TokensProduced,
    DeliveryRegistration,
    DeliveryRegistrationClosed,
    DeliveryRegistrationOpened,
    TokensConsumed,
    TokensInitialized,
    TokensRead,
    replay_armed,
    replay_next_occurrence,
    replay_watermark,
)
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.instance import Instance, Status
from petrus.impetus.petrinet import Arc, ArcMode, Delay, Net, NetPath, Place, Transition

INTAKE, WORK = NetPath("intake"), NetPath("work")
QUEUE, OUT = NetPath("queue"), NetPath("out")


def forward(binding, outputs):
    return {OUT: binding.tokens}


def simple_net() -> Net:
    """intake (source) -> queue -> work (impure) -> out."""
    return Net(
        places=[Place(QUEUE), Place(OUT)],
        transitions=[Transition(INTAKE), Transition(WORK, handler="work")],
        arcs=[Arc(INTAKE, QUEUE), Arc(QUEUE, WORK), Arc(WORK, OUT)],
    )


class TestResume:
    """The constructor: a crash, then a live instance from the durable record alone."""

    def test_resume_rebuilds_marking_watermark_and_continues_the_file(self, tmp_path):
        path = tmp_path / "history.jsonl"
        instance = Instance(simple_net(), handlers={"work": forward}, history=JsonlHistoryStore(path))
        instance.deliver(INTAKE, Token.black(), at=3)

        resumed = Instance.resume(simple_net(), JsonlHistoryStore(path), handlers={"work": forward})

        assert resumed.marking == instance.marking == Marking({QUEUE: (Token.black(),)})
        assert resumed.watermark == 3
        assert resumed.status is instance.status
        # The resumed instance appends to the SAME durable record: one file,
        # one history, before and after the crash.
        firing = resumed.step(at=5)
        assert firing is not None and firing.transition == WORK
        assert resumed.marking == Marking({OUT: (Token.black(),)})
        assert JsonlHistoryStore(path).records == resumed.history.records

    def test_resume_never_reuses_a_recorded_occurrence_id(self, tmp_path):
        path = tmp_path / "history.jsonl"
        instance = Instance(simple_net(), handlers={"work": forward}, history=JsonlHistoryStore(path))
        instance.deliver(INTAKE, Token.black())  # occurrence 1
        instance.run()  # occurrence 2 (work)

        resumed = Instance.resume(simple_net(), JsonlHistoryStore(path), handlers={"work": forward})
        firing = resumed.deliver(INTAKE, Token.black())

        assert firing.occurrence == 3

    def test_resume_rebuilds_the_armed_registrations(self, tmp_path):
        # A handler-refreshed registration (close "default", open "hook")
        # followed by a crash: the resumed instance knows exactly the armed
        # keys the records prove — seal closes precisely them.
        def refresh(binding, outputs):
            return HandlerResult(
                tokens={OUT: binding.tokens},
                opens=(DeliveryRegistration(INTAKE, "hook"),),
                closes=(DeliveryRegistration(INTAKE, "default"),),
            )

        path = tmp_path / "history.jsonl"
        instance = Instance(simple_net(), handlers={"work": refresh}, history=JsonlHistoryStore(path))
        instance.deliver(INTAKE, Token.black())
        instance.run()

        resumed = Instance.resume(simple_net(), JsonlHistoryStore(path), handlers={"work": refresh})
        resumed.seal(INTAKE)

        assert resumed.history.records[-1] == DeliveryRegistrationClosed(INTAKE, "hook", occurrence=None)
        with pytest.raises(ValueError, match="no armed delivery registration"):
            resumed.deliver(INTAKE, Token.black())

    def test_resume_after_seal_takes_no_delivery(self, tmp_path):
        path = tmp_path / "history.jsonl"
        instance = Instance(simple_net(), handlers={"work": forward}, history=JsonlHistoryStore(path))
        instance.seal(INTAKE)

        resumed = Instance.resume(simple_net(), JsonlHistoryStore(path), handlers={"work": forward})

        with pytest.raises(ValueError, match="no armed delivery registration"):
            resumed.deliver(INTAKE, Token.black())

    def test_resume_rebuilds_an_in_flight_occurrence_a_driver_can_complete(self, tmp_path):
        path = tmp_path / "history.jsonl"
        instance = Instance(simple_net(), handlers={"work": forward}, history=JsonlHistoryStore(path))
        instance.deliver(INTAKE, Token.black(), at=3)
        occurrence = instance.begin(instance.candidates()[0], at=4)  # crash mid-firing

        resumed = Instance.resume(simple_net(), JsonlHistoryStore(path), handlers={"work": forward})

        # The rebuilt occurrence IS the recorded one — value-equal, in flight,
        # blocking quiescence exactly as before the crash.
        assert resumed.in_flight == (occurrence,)
        assert resumed.status is Status.RUNNING
        firing = resumed.complete(occurrence, {OUT: occurrence.binding.tokens}, at=9)
        assert firing.occurrence == occurrence.id
        assert resumed.marking == Marking({OUT: (Token.black(),)})
        assert resumed.watermark == 9

    def test_resume_rebuilds_an_in_flight_occurrence_a_driver_can_fail(self, tmp_path):
        path = tmp_path / "history.jsonl"
        instance = Instance(simple_net(), handlers={"work": forward}, history=JsonlHistoryStore(path))
        instance.deliver(INTAKE, Token.black())
        instance.begin(instance.candidates()[0])

        resumed = Instance.resume(simple_net(), JsonlHistoryStore(path), handlers={"work": forward})
        [rebuilt] = resumed.in_flight
        resumed.fail(rebuilt, "crashed worker never reported")

        assert isinstance(resumed.history.records[-1], FiringFailed)
        assert resumed.in_flight == ()

    def test_a_rebuilt_delivered_occurrence_carries_its_delivered_tokens(self):
        # A crash between a delivery's begin and its commit: the rebuilt
        # binding carries the external event's tokens (the initiation record
        # holds them — a source firing selects nothing).
        token = Token("issue", {"id": "goose"})
        history = InMemoryHistoryStore()
        history.extend(
            [
                DeliveryRegistrationOpened(INTAKE, "default", occurrence=None, instant=0),
                ExternalEventDelivered(INTAKE, (token,), identity="occurrence-1", occurrence=1, instant=2),
                FiringBegun(INTAKE, occurrence=1, instant=2),
            ]
        )

        resumed = Instance.resume(simple_net(), history, handlers={"work": forward})
        [rebuilt] = resumed.in_flight

        assert rebuilt.binding.delivered == (token,)
        assert rebuilt.binding.consumed == ()
        resumed.complete(rebuilt, {QUEUE: (token,)})
        assert resumed.marking == Marking({QUEUE: (token,)})

    def test_an_orphan_initiation_is_not_in_flight_but_its_id_never_re_mints(self):
        # An initiation with no begun boundary (a partially persisted batch)
        # is not in flight — but its minted id is a recorded fact, and the
        # counter continues past it.
        history = InMemoryHistoryStore()
        history.extend(
            [
                TokensInitialized(QUEUE, (Token.black(),), instant=0),
                DeliveryRegistrationOpened(INTAKE, "default", occurrence=None, instant=0),
                CandidateSelected(WORK, occurrence=1, instant=1),
            ]
        )

        resumed = Instance.resume(simple_net(), history, handlers={"work": forward})

        assert resumed.in_flight == ()
        firing = resumed.step()
        assert firing is not None and firing.occurrence == 2

    def test_resume_restores_a_pending_delay_and_wakes_it(self, tmp_path):
        # The clock's whole story across a crash, behaviorally: the Delay
        # anchor replays from the movement records, the watermark from the
        # last instant — so the resumed instance owes the same wakeup the
        # crashed one did, and waking it fires the same transition.
        start, out, expire = NetPath("start"), NetPath("out"), NetPath("expire")
        net = Net(
            places=[Place(start), Place(out)],
            transitions=[Transition(expire, timers=(Delay(5),))],
            arcs=[Arc(start, expire), Arc(expire, out)],
        )
        path = tmp_path / "history.jsonl"
        Instance(net, Marking.from_counts({start: 1}), history=JsonlHistoryStore(path))

        resumed = Instance.resume(net, JsonlHistoryStore(path))

        assert resumed.next_maturation == 5
        assert resumed.step() is None  # immature at the watermark, exactly as before the crash
        assert resumed.wake(5) is not None
        firing = resumed.step()
        assert firing is not None and firing.transition == expire
        assert resumed.marking == Marking({out: (Token.black(),)})

    def test_resume_rejects_an_empty_history(self):
        with pytest.raises(ValueError, match="empty history"):
            Instance.resume(simple_net(), InMemoryHistoryStore(), handlers={"work": forward})

    def test_resume_rejects_token_records_on_a_foreign_place(self):
        # The marking is live state like the armed set and the in-flight set:
        # a token on a place this net does not have is a foreign or corrupted
        # trace, refused — not silently carried as inert cargo.
        history = InMemoryHistoryStore()
        history.append(TokensInitialized(NetPath("ghost"), (Token.black(),), instant=0))
        with pytest.raises(ValueError, match="ghost.*not a place of this net"):
            Instance.resume(simple_net(), history, handlers={"work": forward})

    def test_resume_rejects_a_non_monotone_history(self):
        # The single writer appends monotone instants; a trace whose instants
        # step backwards is corrupted or reordered, and resuming over it
        # would let the next append record an instant earlier than a fact.
        history = InMemoryHistoryStore()
        history.extend(
            [
                TokensInitialized(QUEUE, (Token.black(),), instant=10),
                DeliveryRegistrationOpened(INTAKE, "default", occurrence=None, instant=5),
            ]
        )
        with pytest.raises(ValueError, match="replay divergence.*steps backwards"):
            Instance.resume(simple_net(), history, handlers={"work": forward})

    def test_resume_rejects_a_scheduled_selection_on_a_source(self):
        # The begin/deliver door partition, ported to the rebuilt traffic
        # [convention 36]: begin() refuses to schedule a source live, so a
        # trace claiming it did is divergence, not a binding to rebuild.
        history = InMemoryHistoryStore()
        history.extend(
            [
                DeliveryRegistrationOpened(INTAKE, "default", occurrence=None, instant=0),
                CandidateSelected(INTAKE, occurrence=1, instant=1),
                FiringBegun(INTAKE, occurrence=1, instant=1),
            ]
        )
        with pytest.raises(ValueError, match="scheduled selection on a source transition"):
            Instance.resume(simple_net(), history, handlers={"work": forward})

    def test_resume_rejects_a_delivery_on_a_non_source(self):
        history = InMemoryHistoryStore()
        history.extend(
            [
                ExternalEventDelivered(WORK, (Token.black(),), identity="occurrence-1", occurrence=1, instant=1),
                FiringBegun(WORK, occurrence=1, instant=1),
            ]
        )
        with pytest.raises(ValueError, match="only a source transition takes delivery"):
            Instance.resume(simple_net(), history, handlers={"work": forward})

    def test_resume_rejects_consumed_records_that_do_not_match_the_consume_arcs(self):
        # A live begin accounts one consume per consume arc; a begun occurrence
        # whose trace lacks them would rebuild a binding begin() could never
        # mint — completing it would deposit without ever having consumed.
        history = InMemoryHistoryStore()
        history.extend(
            [
                TokensInitialized(QUEUE, (Token.black(),), instant=0),
                CandidateSelected(WORK, occurrence=1, instant=1),
                FiringBegun(WORK, occurrence=1, instant=1),
            ]
        )
        with pytest.raises(ValueError, match="do not match the transition's consume arcs"):
            Instance.resume(simple_net(), history, handlers={"work": forward})

    def test_resume_rejects_a_registration_on_a_foreign_node(self):
        history = InMemoryHistoryStore()
        history.append(DeliveryRegistrationOpened(NetPath("ghost"), "default", occurrence=None, instant=0))
        with pytest.raises(ValueError, match="ghost.*not a transition of this net"):
            Instance.resume(simple_net(), history, handlers={"work": forward})

    def test_resume_rejects_a_registration_on_a_non_source(self):
        history = InMemoryHistoryStore()
        history.append(DeliveryRegistrationOpened(WORK, "default", occurrence=None, instant=0))
        with pytest.raises(ValueError, match="input arcs"):
            Instance.resume(simple_net(), history, handlers={"work": forward})

    def test_resume_rejects_an_in_flight_occurrence_on_a_foreign_transition(self):
        history = InMemoryHistoryStore()
        history.extend(
            [
                CandidateSelected(NetPath("ghost"), occurrence=1, instant=0),
                FiringBegun(NetPath("ghost"), occurrence=1, instant=0),
            ]
        )
        with pytest.raises(ValueError, match="ghost.*not a transition of this net"):
            Instance.resume(simple_net(), history, handlers={"work": forward})

    def _reading_net(self) -> Net:
        """queue -> work (impure, also reading gate) -> out."""
        gate = NetPath("gate")
        return Net(
            places=[Place(QUEUE), Place(gate), Place(OUT)],
            transitions=[Transition(WORK, handler="work")],
            arcs=[Arc(QUEUE, WORK), Arc(gate, WORK, mode=ArcMode.READ), Arc(WORK, OUT)],
        )

    def test_resume_rebuilds_an_in_flight_occurrence_with_its_recorded_read_selections(self, tmp_path):
        # The old read-arc refusal is gone: begin records its read selections
        # (debt 2026-07-09T2330Z, recording half), so the rebuilt binding
        # carries the exact recorded reads and never consults the live
        # marking — the handler observes across the crash exactly what it
        # observed before it.
        gate, settings = NetPath("gate"), Token("Config", {"mode": "strict"})
        path = tmp_path / "history.jsonl"
        instance = Instance(
            self._reading_net(),
            Marking({QUEUE: (Token.black(),), gate: (settings,)}),
            handlers={"work": forward},
            history=JsonlHistoryStore(path),
        )
        occurrence = instance.begin(instance.candidates()[0], at=2)  # crash mid-firing

        resumed = Instance.resume(self._reading_net(), JsonlHistoryStore(path), handlers={"work": forward})

        assert resumed.in_flight == (occurrence,)
        [rebuilt] = resumed.in_flight
        assert rebuilt.binding.read == ((gate, (settings,)),)
        firing = resumed.complete(rebuilt, {OUT: rebuilt.binding.tokens}, at=3)
        assert firing.occurrence == occurrence.id
        assert resumed.marking == Marking({gate: (settings,), OUT: (Token.black(),)})

    def test_resume_rejects_read_records_that_do_not_match_the_read_arcs(self):
        # The consume-arc validation's read mirror: a live begin records one
        # read per read arc, in input-arc order, weight tokens each — a begun
        # occurrence whose trace lacks its read fact rebuilds a binding
        # begin() could never have minted.
        history = InMemoryHistoryStore()
        history.extend(
            [
                TokensInitialized(QUEUE, (Token.black(),), instant=0),
                TokensInitialized(NetPath("gate"), (Token.black(),), instant=0),
                CandidateSelected(WORK, occurrence=1, instant=1),
                FiringBegun(WORK, occurrence=1, instant=1),
                TokensConsumed(QUEUE, (Token.black(),), occurrence=1, instant=1),
            ]
        )
        with pytest.raises(ValueError, match="read selections do not match the transition's read arcs"):
            Instance.resume(self._reading_net(), history, handlers={"work": forward})

    def test_resume_rejects_a_consume_record_count_that_disagrees_with_the_arc_weight(self):
        # The shape rule's count conjunct, exercised directly: a weight-2
        # consume arc whose begun occurrence recorded only one token rebuilds
        # a binding begin() could never have minted.
        a, t, b = NetPath("a"), NetPath("t"), NetPath("b")
        net = Net(
            places=[Place(a), Place(b)],
            transitions=[Transition(t)],
            arcs=[Arc(a, t, weight=2), Arc(t, b)],
        )
        token = Token.black()
        history = InMemoryHistoryStore()
        history.extend(
            [
                TokensInitialized(a, (token, token), instant=0),
                CandidateSelected(t, occurrence=1, instant=1),
                FiringBegun(t, occurrence=1, instant=1),
                TokensConsumed(a, (token,), occurrence=1, instant=1),
            ]
        )
        with pytest.raises(ValueError, match="consume selections do not match the transition's consume arcs"):
            Instance.resume(net, history)

    def test_resume_rejects_a_read_record_count_that_disagrees_with_the_arc_weight(self):
        # The read mirror of the count conjunct: two read tokens recorded
        # against a weight-1 read arc.
        gate, token = NetPath("gate"), Token("Config")
        history = InMemoryHistoryStore()
        history.extend(
            [
                TokensInitialized(QUEUE, (Token.black(),), instant=0),
                TokensInitialized(gate, (token, token), instant=0),
                CandidateSelected(WORK, occurrence=1, instant=1),
                FiringBegun(WORK, occurrence=1, instant=1),
                TokensConsumed(QUEUE, (Token.black(),), occurrence=1, instant=1),
                TokensRead(gate, (token, token), occurrence=1, instant=1),
            ]
        )
        with pytest.raises(ValueError, match="read selections do not match the transition's read arcs"):
            Instance.resume(self._reading_net(), history, handlers={"work": forward})


class TestReplayArmed:
    """The registration lifecycle's replay fold — the armed projection, direct."""

    def test_folds_opens_and_closes_in_order(self):
        history = InMemoryHistoryStore()
        history.extend(
            [
                DeliveryRegistrationOpened(INTAKE, "default", occurrence=None, instant=0),
                DeliveryRegistrationOpened(INTAKE, "hook", occurrence=1, instant=1),
                DeliveryRegistrationClosed(INTAKE, "default", occurrence=1, instant=1),
            ]
        )
        assert replay_armed(history) == {INTAKE: {"hook"}}

    def test_a_source_closed_to_nothing_stays_present_and_empty(self):
        history = InMemoryHistoryStore()
        history.extend(
            [
                DeliveryRegistrationOpened(INTAKE, "default", occurrence=None, instant=0),
                DeliveryRegistrationClosed(INTAKE, "default", occurrence=None, instant=1),
            ]
        )
        assert replay_armed(history) == {INTAKE: set()}

    def test_an_open_of_an_armed_key_is_replay_divergence(self):
        history = InMemoryHistoryStore()
        history.extend(
            [
                DeliveryRegistrationOpened(INTAKE, "default", occurrence=None, instant=0),
                DeliveryRegistrationOpened(INTAKE, "default", occurrence=None, instant=1),
            ]
        )
        with pytest.raises(ValueError, match="replay divergence.*opened while armed"):
            replay_armed(history)

    def test_a_close_of_an_unarmed_key_is_replay_divergence(self):
        history = InMemoryHistoryStore()
        history.append(DeliveryRegistrationClosed(INTAKE, "default", occurrence=None, instant=0))
        with pytest.raises(ValueError, match="replay divergence.*closed while not armed"):
            replay_armed(history)


class TestReplayInFlight:
    """The occurrence lifecycle's replay fold — begun without ended, direct."""

    def test_rebuilds_begun_occurrences_with_their_consumed_selections_in_order(self):
        other = NetPath("other")
        first, second = Token("a"), Token("b")
        history = InMemoryHistoryStore()
        history.extend(
            [
                CandidateSelected(WORK, occurrence=1, instant=1),
                FiringBegun(WORK, occurrence=1, instant=1),
                TokensConsumed(QUEUE, (first,), occurrence=1, instant=1),
                TokensConsumed(other, (second,), occurrence=1, instant=1),
            ]
        )
        [occurrence] = replay_in_flight(history)
        assert occurrence.id == 1
        assert occurrence.binding.transition == WORK
        assert occurrence.binding.consumed == ((QUEUE, (first,)), (other, (second,)))
        assert occurrence.records == tuple(history.records[1:])

    def test_ended_occurrences_are_not_in_flight(self):
        history = InMemoryHistoryStore()
        history.extend(
            [
                CandidateSelected(WORK, occurrence=1, instant=1),
                FiringBegun(WORK, occurrence=1, instant=1),
                FiringCompleted(WORK, occurrence=1, instant=2),
                CandidateSelected(WORK, occurrence=2, instant=3),
                FiringBegun(WORK, occurrence=2, instant=3),
                FiringFailed(WORK, "boom", occurrence=2, instant=4),
            ]
        )
        assert replay_in_flight(history) == ()

    def test_rebuilds_a_begun_occurrence_with_its_recorded_read_selections(self):
        # The fold reads the read half straight off the TokensRead records —
        # in their recorded input-arc order, beside the consumed selections.
        gate, settings = NetPath("gate"), Token("Config", {"mode": "strict"})
        history = InMemoryHistoryStore()
        history.extend(
            [
                CandidateSelected(WORK, occurrence=1, instant=1),
                FiringBegun(WORK, occurrence=1, instant=1),
                TokensConsumed(QUEUE, (Token.black(),), occurrence=1, instant=1),
                TokensRead(gate, (settings,), occurrence=1, instant=1),
            ]
        )
        [occurrence] = replay_in_flight(history)
        assert occurrence.binding.consumed == ((QUEUE, (Token.black(),)),)
        assert occurrence.binding.read == ((gate, (settings,)),)
        assert occurrence.records == tuple(history.records[1:])

    def test_a_delivered_occurrence_rebuilds_with_its_delivered_tokens(self):
        token = Token("issue", {"id": "goose"})
        history = InMemoryHistoryStore()
        history.extend(
            [
                ExternalEventDelivered(INTAKE, (token,), identity="occurrence-1", occurrence=1, instant=1),
                FiringBegun(INTAKE, occurrence=1, instant=1),
            ]
        )
        [occurrence] = replay_in_flight(history)
        assert occurrence.binding.delivered == (token,)
        assert occurrence.binding.consumed == ()

    def test_an_initiation_alone_is_not_in_flight(self):
        history = InMemoryHistoryStore()
        history.append(CandidateSelected(WORK, occurrence=1, instant=1))
        assert replay_in_flight(history) == ()

    def test_a_consume_with_no_begun_boundary_is_replay_divergence(self):
        history = InMemoryHistoryStore()
        history.append(TokensConsumed(QUEUE, (Token.black(),), occurrence=1, instant=1))
        with pytest.raises(ValueError, match="replay divergence.*no begun boundary"):
            replay_in_flight(history)

    def test_a_begun_boundary_with_no_initiation_is_replay_divergence(self):
        history = InMemoryHistoryStore()
        history.append(FiringBegun(WORK, occurrence=1, instant=1))
        with pytest.raises(ValueError, match="replay divergence.*no initiation"):
            replay_in_flight(history)

    def test_end_records_with_no_terminal_boundary_are_a_torn_batch(self):
        # complete() commits its movements, effects, and the
        # terminal record as one batch [convention 45]; end records for a
        # begun-not-ended occurrence mean the batch tore — rebuilding it as
        # never-run would re-execute a handler whose deposit already landed.
        # (ActivityCompleted is deliberately NOT this shape: it commits alone
        # by design — the projection-pending pin lives in test_activity_seam.)
        history = InMemoryHistoryStore()
        history.extend(
            [
                CandidateSelected(WORK, occurrence=1, instant=1),
                FiringBegun(WORK, occurrence=1, instant=1),
                TokensConsumed(QUEUE, (Token.black(),), occurrence=1, instant=1),
                TokensProduced(OUT, (Token.black(),), occurrence=1, instant=2),
            ]
        )
        with pytest.raises(ValueError, match="replay divergence.*torn commit batch"):
            replay_in_flight(history)


class TestReplayWatermark:
    """The watermark projection — the last instant, validated monotone."""

    def test_the_watermark_is_the_last_records_instant(self):
        history = InMemoryHistoryStore()
        history.extend(
            [
                TokensInitialized(QUEUE, (Token.black(),), instant=0),
                CandidateSelected(WORK, occurrence=1, instant=7),
            ]
        )
        assert replay_watermark(history) == 7

    def test_a_backwards_instant_is_replay_divergence(self):
        history = InMemoryHistoryStore()
        history.extend(
            [
                TokensInitialized(QUEUE, (Token.black(),), instant=10),
                CandidateSelected(WORK, occurrence=1, instant=5),
            ]
        )
        with pytest.raises(ValueError, match="replay divergence.*steps backwards"):
            replay_watermark(history)

    def test_an_empty_history_proves_no_watermark(self):
        with pytest.raises(ValueError, match="empty history"):
            replay_watermark(InMemoryHistoryStore())


class TestReplayNextOccurrence:
    """The occurrence-counter projection — one past every spent id, orphans included."""

    def test_an_orphan_initiations_id_is_spent(self):
        history = InMemoryHistoryStore()
        history.append(CandidateSelected(WORK, occurrence=3, instant=1))
        assert replay_next_occurrence(history) == 4

    def test_none_correlations_spend_nothing(self):
        history = InMemoryHistoryStore()
        history.append(DeliveryRegistrationOpened(INTAKE, "default", occurrence=None, instant=0))
        assert replay_next_occurrence(history) == 1

    def test_a_stray_terminal_records_id_is_spent(self):
        # Wider than the minting sites on purpose: on a foreign or partial
        # trace, never re-minting a referenced id outranks tight bookkeeping.
        history = InMemoryHistoryStore()
        history.append(FiringFailed(WORK, "stray", occurrence=7, instant=1))
        assert replay_next_occurrence(history) == 8
