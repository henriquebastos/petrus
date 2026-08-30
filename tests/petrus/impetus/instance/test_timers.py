"""
Impetus-native tests for timers: per-binding age-anchored maturation over the
clock watermark.

A transition timer is declared on the transition but evaluated per firing
binding: a duration timer (``Delay``) matures a binding at the youngest
recorded entry instant among its consume/read-bound tokens plus the duration;
an absolute timer (``Until``) matures every binding at its declared instant
[DR 2026-07-08 timers-keyed-per-firing-binding-age-anchored]. "Now" is the
clock watermark — the monotone instant of the latest appended record; semantic
time advances only at appends, any record advances the clock, and timer state
is derived from marking and history, never stored. The adapter's wakeup enters
as the category-2 ``TimerMatured`` record; maturation enables, the scheduler
alone chooses firing [DR 2026-07-08 time-projection-virtual-clock-watermark].

Navigator rulings (2026-07-09, slice 9): every record carries an ``instant``
field stamped at append (default 0, the logical epoch); instants are opaque
totally-ordered values and the construction ``at=`` anchors the initial
marking; every history-appending method takes ``at=`` (None = no advance,
earlier instants monotone-clamped) and ``wake(at)`` derives the occasioning
maturation itself, suppressing the record when nothing derives matured;
``Transition.timers`` is a tuple (conjunction, mirroring guards).
"""

from __future__ import annotations

# Pip imports
import pytest

# Internal imports
from petrus.impetus.petrinet import candidates, maturation, next_maturation
from petrus.impetus.history import (
    InstanceCreated,
    TimerMatured,
    TokensConsumed,
    TokensInitialized,
    TokensProduced,
    entry_instants,
    replay_marking,
)
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.instance import Instance, Status
from petrus.impetus.petrinet import Arc, ArcMode, Delay, Net, NetPath, Place, Transition, Until

PENDING, EXPIRE, EXPIRED = NetPath("pending"), NetPath("expire"), NetPath("expired")


def expiry_net(*timers: Delay | Until) -> Net:
    """pending -> expire -> expired, with the timers under test on expire."""
    return Net(
        places=[Place(PENDING), Place(EXPIRED)],
        transitions=[Transition(EXPIRE, timers=timers)],
        arcs=[Arc(PENDING, EXPIRE), Arc(EXPIRE, EXPIRED)],
    )


class TestTimerDeclarations:
    """The schema admits the two ratified timer forms and rejects what cannot be honored."""

    def test_a_timer_must_be_a_delay_or_an_until(self):
        # The two declared encodings only — anything else would surface later
        # as a broken maturation instead of a declared mismatch.
        with pytest.raises(ValueError, match=r"timer must be a Delay or an Until, got 'soon': t"):
            Transition(NetPath("t"), timers=("soon",))

    def test_timers_on_a_source_transition_are_rejected(self):
        # A timer is enabledness machinery and source transitions are excluded
        # from enabledness — they fire only on external delivery [ADR 0005,
        # DR source-transition-ingress]; same rationale as guards-on-source.
        with pytest.raises(ValueError, match=r"transition src: timers on a source transition cannot be honored"):
            Net(
                places=[Place(NetPath("out"))],
                transitions=[Transition(NetPath("src"), timers=(Delay(10),))],
                arcs=[Arc(NetPath("src"), NetPath("out"))],
            )

    def test_a_delay_with_only_inhibitor_inputs_is_rejected(self):
        # Inhibitor arcs contribute no anchor — absence has no entry instant —
        # so a duration timer there has nothing to mature from [DR timers-keyed].
        with pytest.raises(ValueError, match=r"transition t: a duration timer has no anchor"):
            Net(
                places=[Place(NetPath("hold")), Place(NetPath("out"))],
                transitions=[Transition(NetPath("t"), handler="emit", timers=(Delay(10),))],
                arcs=[Arc(NetPath("hold"), NetPath("t"), mode=ArcMode.INHIBIT), Arc(NetPath("t"), NetPath("out"))],
            )

    def test_an_until_with_only_inhibitor_inputs_is_legal(self):
        # An absolute instant needs no anchor [DR timers-keyed].
        net = Net(
            places=[Place(NetPath("hold")), Place(NetPath("out"))],
            transitions=[Transition(NetPath("t"), handler="emit", timers=(Until(100),))],
            arcs=[Arc(NetPath("hold"), NetPath("t"), mode=ArcMode.INHIBIT), Arc(NetPath("t"), NetPath("out"))],
        )
        assert net.transitions[NetPath("t")].timers == (Until(100),)


class TestRecordInstants:
    """Every record carries the instant of its append; the watermark is monotone."""

    def net(self) -> Net:
        return Net(
            places=[Place(NetPath("inbox"))],
            transitions=[Transition(NetPath("ingest"))],
            arcs=[Arc(NetPath("ingest"), NetPath("inbox"))],
        )

    def test_construction_stamps_the_initial_records_with_its_instant(self):
        a = NetPath("a")
        net = Net(places=[Place(a)], transitions=[], arcs=[])
        instance = Instance(net, Marking({a: (Token.black(),)}), at=5)
        assert instance.history.records == (
            InstanceCreated(instance.instance_id, instant=5),
            TokensInitialized(a, (Token.black(),), instant=5),
        )
        assert instance.watermark == 5

    def test_delivery_stamps_the_event_and_its_firing_records(self):
        instance = Instance(self.net())
        accepted = instance.accept_delivery(NetPath("ingest"), Token.black(), at=3, identity="timed-event")
        instance.complete_delivery(accepted, at=3)
        assert {record.instant for record in instance.history} == {0, 3}  # registration at 0, delivery at 3
        assert instance.watermark == 3

    def test_an_earlier_instant_is_clamped_to_the_watermark(self):
        # The single writer enforces monotonicity by clamping, not raising
        # [DR time-projection-virtual-clock-watermark].
        instance = Instance(self.net())
        accepted = instance.accept_delivery(NetPath("ingest"), Token.black(), at=7, identity="later-event")
        instance.complete_delivery(accepted, at=7)
        accepted = instance.accept_delivery(NetPath("ingest"), Token.black(), at=2, identity="clamped-event")
        firing = instance.complete_delivery(accepted, at=2)
        assert instance.watermark == 7
        assert all(record.instant == 7 for record in firing.records)

    def test_no_instant_means_no_advance(self):
        instance = Instance(self.net())
        accepted = instance.accept_delivery(NetPath("ingest"), Token.black(), at=4, identity="advanced-event")
        instance.complete_delivery(accepted, at=4)
        accepted = instance.accept_delivery(NetPath("ingest"), Token.black(), identity="unstamped-event")
        firing = instance.complete_delivery(accepted)
        assert instance.watermark == 4
        assert all(record.instant == 4 for record in firing.records)

    def test_a_maturation_cannot_be_observed_before_it_happened(self):
        # The record's instant is the observed instant of the wakeup; a
        # maturation observed before it derived would assert a false fact.
        with pytest.raises(ValueError, match=r"observed at 3, before its maturation instant 5"):
            TimerMatured(maturation_instant=5, instant=3)

    def test_replay_rebuilds_the_marking_from_instant_stamped_records(self):
        instance = Instance(self.net())
        accepted = instance.accept_delivery(NetPath("ingest"), Token.black(), at=9, identity="replay-event")
        instance.complete_delivery(accepted, at=9)
        assert replay_marking(instance.history) == instance.marking


class TestEntryInstants:
    """The per-place entry instants are a projection of recorded movements."""

    def test_entry_instants_mirror_the_queues_they_annotate(self):
        a, b = NetPath("a"), NetPath("b")
        history = InMemoryHistoryStore()
        history.append(TokensInitialized(a, (Token.black(), Token("X")), instant=0))
        history.append(TokensProduced(b, (Token("Y"),), occurrence=1, instant=4))
        history.append(TokensConsumed(a, (Token.black(),), occurrence=1, instant=6))
        assert entry_instants(history) == {a: (0,), b: (4,)}

    def test_consume_removes_the_front_most_equal_occurrence(self):
        # Two equal tokens entered at different instants: consuming one frees
        # the front entry, exactly as Marking.consume removes the front token.
        a = NetPath("a")
        history = InMemoryHistoryStore()
        history.append(TokensInitialized(a, (Token.black(),), instant=0))
        history.append(TokensProduced(a, (Token.black(),), occurrence=1, instant=5))
        history.append(TokensConsumed(a, (Token.black(),), occurrence=1, instant=7))
        assert entry_instants(history) == {a: (5,)}


class TestMaturation:
    """maturation: the instant every declared timer has matured — the pure unit."""

    def test_a_delay_matures_at_anchor_plus_duration(self):
        assert maturation((Delay(10),), anchor=5) == 15

    def test_an_until_matures_at_its_instant_regardless_of_anchor(self):
        assert maturation((Until(30),), anchor=5) == 30

    def test_conjunction_matures_when_the_last_timer_does(self):
        assert maturation((Delay(10), Until(30)), anchor=0) == 30
        assert maturation((Delay(50), Until(30)), anchor=0) == 50

    def test_an_until_only_binding_needs_no_anchor(self):
        # The docstring's defended looseness, pinned: an inhibitor-only Until
        # transition genuinely feeds anchor=None [convention 22].
        assert maturation((Until(30),), anchor=None) == 30

    def test_no_timers_means_no_maturation(self):
        assert maturation((), anchor=0) is None


class TestTimedEnabledness:
    """Maturation gates the binding purely: not yet matured is not enabled."""

    def test_a_timed_net_requires_the_clock(self):
        # Enabledness over a timed net without the watermark and entry
        # instants would silently read time as never passing — refuse instead.
        net = expiry_net(Delay(10))
        with pytest.raises(ValueError, match=r"timed net"):
            candidates(net, Marking({PENDING: (Token.black(),)}))

    def test_a_watermark_without_entry_instants_is_rejected(self):
        # The clock is a pair; the missing half is named, never a raw
        # IndexError from the anchor lookup.
        net = expiry_net(Delay(10))
        with pytest.raises(ValueError, match=r"entry instants for place pending are missing or misaligned"):
            candidates(net, Marking({PENDING: (Token.black(),)}), watermark=99)

    def test_candidates_returns_the_binding_once_matured(self):
        # The pure unit's two branches, beside its sibling next_maturation:
        # immature at 0, enabled at 12.
        net = expiry_net(Delay(10))
        marking = Marking({PENDING: (Token.black(),)})
        assert candidates(net, marking, watermark=0, entry_instants={PENDING: (2,)}) == []
        [binding] = candidates(net, marking, watermark=12, entry_instants={PENDING: (2,)})
        assert binding.transition == EXPIRE

    def test_an_immature_binding_is_not_enabled(self):
        instance = Instance(expiry_net(Delay(10)), Marking({PENDING: (Token.black(),)}))
        assert instance.candidates() == []
        assert instance.enabled_transitions() == []

    def test_the_binding_matures_delay_after_its_token_entered(self):
        # The anchor is the token's recorded entry instant, not the net's age:
        # a token delivered at 4 matures the binding at 14.
        net = Net(
            places=[Place(PENDING), Place(EXPIRED)],
            transitions=[Transition(NetPath("src")), Transition(EXPIRE, timers=(Delay(10),))],
            arcs=[Arc(NetPath("src"), PENDING), Arc(PENDING, EXPIRE), Arc(EXPIRE, EXPIRED)],
        )
        instance = Instance(net)
        accepted = instance.accept_delivery(NetPath("src"), Token.black(), at=4, identity="delay-anchor")
        instance.complete_delivery(accepted, at=4)
        assert instance.next_maturation == 14

    def test_a_read_bound_token_anchors_the_binding_like_a_consumed_one(self):
        # The youngest bound token anchors [DR timers-keyed]: config entered at
        # 8 after pending's 2, so the binding matures at 8 + 10.
        config = NetPath("config")
        net = Net(
            places=[Place(PENDING), Place(config), Place(EXPIRED)],
            transitions=[Transition(NetPath("src")), Transition(EXPIRE, timers=(Delay(10),))],
            arcs=[
                Arc(NetPath("src"), config),
                Arc(PENDING, EXPIRE),
                Arc(config, EXPIRE, mode=ArcMode.READ),
                Arc(EXPIRE, EXPIRED),
            ],
        )
        instance = Instance(net, Marking({PENDING: (Token.black(),)}), at=2)
        accepted = instance.accept_delivery(NetPath("src"), Token.black(), at=8, identity="read-anchor")
        instance.complete_delivery(accepted, at=8)
        assert instance.next_maturation == 18

    def test_a_binding_failing_its_guard_is_not_waiting_on_time(self):
        # Guards gate before timers: a binding the guards reject is not
        # enabled-but-for-timer and derives no maturation.
        net = Net(
            places=[Place(PENDING), Place(EXPIRED)],
            transitions=[Transition(EXPIRE, guards=("never",), timers=(Delay(10),))],
            arcs=[Arc(PENDING, EXPIRE), Arc(EXPIRE, EXPIRED)],
        )
        instance = Instance(net, Marking({PENDING: (Token.black(),)}), guards={"never": lambda b: False})
        assert instance.next_maturation is None

    def test_a_guard_failed_head_does_not_hide_a_deeper_bindings_maturation(self):
        # The timer leg of debt 2026-07-09T2110Z: with the head selection
        # rejected by the guard, the deeper guard-passing binding is the one
        # waiting on time — its maturation is the wakeup owed, where single-
        # binding enumeration derived none and the net slept forever.
        small, big = Token("Payment", {"amount": 40}), Token("Payment", {"amount": 150})
        net = Net(
            places=[Place(PENDING), Place(EXPIRED)],
            transitions=[Transition(EXPIRE, guards=("big",), timers=(Delay(10),))],
            arcs=[Arc(PENDING, EXPIRE), Arc(EXPIRE, EXPIRED)],
        )
        guards = {"big": lambda b: b.peeked[0].data["amount"] >= 100}
        marking = Marking({PENDING: (small, big)})
        assert candidates(net, marking, guards, watermark=12, entry_instants={PENDING: (0, 8)}) == []
        assert next_maturation(net, marking, guards, watermark=12, entry_instants={PENDING: (0, 8)}) == 18
        [binding] = candidates(net, marking, guards, watermark=18, entry_instants={PENDING: (0, 8)})
        assert binding.tokens == (big,)

    def test_next_maturation_is_none_when_nothing_waits(self):
        instance = Instance(expiry_net(Delay(10)))
        assert instance.next_maturation is None

    def test_next_maturation_derives_from_the_supplied_clock(self):
        # The pure unit, beside its pipeline coverage: anchors come from the
        # entry instants, position-aligned with the queues.
        net = expiry_net(Delay(10))
        marking = Marking({PENDING: (Token.black(),)})
        assert next_maturation(net, marking, watermark=0, entry_instants={PENDING: (2,)}) == 12
        assert (
            next_maturation(net, marking, watermark=12, entry_instants={PENDING: (2,)}) is None
        )  # matured: enabled, not pending


class TestWakeup:
    """wake(at): the adapter's wakeup made into the category-2 record."""

    def test_wake_records_the_derived_maturation_and_enables_the_binding(self):
        instance = Instance(expiry_net(Delay(10)), Marking({PENDING: (Token.black(),)}))
        record = instance.wake(at=10)
        assert record == TimerMatured(maturation_instant=10, instant=10)
        assert record in instance.history.records
        assert instance.watermark == 10
        assert instance.enabled_transitions() == [EXPIRE]

    def test_maturation_enables_but_never_fires(self):
        # No urgency: the scheduler alone chooses firing [DR timers-keyed].
        instance = Instance(expiry_net(Delay(10)), Marking({PENDING: (Token.black(),)}))
        instance.wake(at=10)
        assert instance.marking == Marking({PENDING: (Token.black(),)})
        firing = instance.step()
        assert firing is not None and firing.transition == EXPIRE
        assert instance.marking == Marking({EXPIRED: (Token.black(),)})

    def test_a_late_wakeup_is_observed_at_its_own_instant(self):
        instance = Instance(expiry_net(Delay(10)), Marking({PENDING: (Token.black(),)}))
        record = instance.wake(at=13)
        assert record == TimerMatured(maturation_instant=10, instant=13)

    def test_an_early_wakeup_is_suppressed(self):
        # Nothing derives matured at 5, so there is no fact to record
        # [DR time-projection: the adapter MAY suppress].
        instance = Instance(expiry_net(Delay(10)), Marking({PENDING: (Token.black(),)}))
        assert instance.wake(at=5) is None
        assert instance.watermark == 0
        assert not [r for r in instance.history if isinstance(r, TimerMatured)]

    def test_a_stale_wakeup_after_the_binding_was_consumed_is_harmless(self):
        # The binding fired before the wakeup landed: no maturation derives,
        # no firing, no error [ES-007 seed list].
        instance = Instance(expiry_net(Delay(10)), Marking({PENDING: (Token.black(),)}))
        instance.wake(at=10)
        instance.step()
        assert instance.wake(at=20) is None
        assert instance.status is Status.TERMINATED


class TestWatermarkAdvance:
    """Any record advances the clock — no timer-matured record needed."""

    def test_an_unrelated_event_matures_the_timed_binding(self):
        other = NetPath("other")
        net = Net(
            places=[Place(PENDING), Place(other), Place(EXPIRED)],
            transitions=[Transition(NetPath("src")), Transition(EXPIRE, timers=(Delay(10),))],
            arcs=[Arc(NetPath("src"), other), Arc(PENDING, EXPIRE), Arc(EXPIRE, EXPIRED)],
        )
        instance = Instance(net, Marking({PENDING: (Token.black(),)}))
        accepted = instance.accept_delivery(NetPath("src"), Token.black(), at=12, identity="maturing-event")
        instance.complete_delivery(accepted, at=12)
        assert instance.enabled_transitions() == [EXPIRE]
        assert not [r for r in instance.history if isinstance(r, TimerMatured)]

    def test_a_step_at_an_instant_proves_time_reached_it(self):
        # step(at=15) selects under the advanced clock; the selection record
        # carries the instant that justified the maturity judgment.
        instance = Instance(expiry_net(Delay(10)), Marking({PENDING: (Token.black(),)}))
        firing = instance.step(at=15)
        assert firing is not None and firing.transition == EXPIRE
        assert instance.watermark == 15

    def test_a_step_that_selects_nothing_advances_nothing(self):
        # No record was appended, so semantic time never reached the probe.
        instance = Instance(expiry_net(Delay(10)), Marking({PENDING: (Token.black(),)}))
        assert instance.step(at=5) is None
        assert instance.watermark == 0


class TestTimedStatus:
    """A sleeping instance is running, not terminated."""

    def test_a_sleeping_instance_is_running(self):
        # Quiescence requires no derived future maturation
        # [firing-semantics.md Termination]: waiting on time is not the end.
        instance = Instance(expiry_net(Delay(10)), Marking({PENDING: (Token.black(),)}))
        assert not instance.is_quiescent
        assert instance.status is Status.RUNNING

    def test_the_instance_ends_only_after_the_matured_binding_fires(self):
        instance = Instance(expiry_net(Delay(10)), Marking({PENDING: (Token.black(),)}))
        instance.wake(at=10)
        assert instance.status is Status.RUNNING
        instance.step()
        assert instance.status is Status.TERMINATED


class TestRatifiedScenarios:
    """The ES-007 seed scenarios, driven end to end."""

    def test_concurrent_bindings_mature_in_anchor_order(self):
        # Three tokens arriving at 1 < 2 < 3 each expire delay-10 after ITS
        # arrival — the problem transition-keyed timers cannot express
        # [DR timers-keyed]. FIFO selection surfaces them front-first, so each
        # wakeup matures exactly the oldest binding.
        net = Net(
            places=[Place(PENDING), Place(EXPIRED)],
            transitions=[Transition(NetPath("src")), Transition(EXPIRE, timers=(Delay(10),))],
            arcs=[Arc(NetPath("src"), PENDING), Arc(PENDING, EXPIRE), Arc(EXPIRE, EXPIRED)],
        )
        instance = Instance(net)
        for arrival in (1, 2, 3):
            accepted = instance.accept_delivery(
                NetPath("src"), Token.black(), at=arrival, identity=f"arrival-{arrival}"
            )
            instance.complete_delivery(accepted, at=arrival)
        for maturity in (11, 12, 13):
            assert instance.next_maturation == maturity
            assert instance.wake(at=maturity) == TimerMatured(maturation_instant=maturity, instant=maturity)
            assert instance.step() is not None
        assert instance.marking == Marking({EXPIRED: (Token.black(),) * 3})
        assert instance.next_maturation is None

    def test_an_until_is_indifferent_to_enablement_churn(self):
        # Inhibitor flapping between declaration and D moves nothing: the
        # deadline recomputes from the same absolute instant [DR timers-keyed].
        hold, drain = NetPath("hold"), NetPath("drain")
        net = Net(
            places=[Place(PENDING), Place(hold), Place(EXPIRED)],
            transitions=[Transition(drain), Transition(EXPIRE, timers=(Until(100),))],
            arcs=[
                Arc(hold, drain),
                Arc(PENDING, EXPIRE),
                Arc(hold, EXPIRE, mode=ArcMode.INHIBIT),
                Arc(EXPIRE, EXPIRED),
            ],
        )
        instance = Instance(net, Marking({PENDING: (Token.black(),), hold: (Token.black(),)}))
        assert instance.step(at=50) is not None  # drain fires: the inhibitor stops flapping
        assert instance.candidates() == []  # unblocked but immature
        assert instance.next_maturation == 100
        instance.wake(at=100)
        assert instance.enabled_transitions() == [EXPIRE]

    def test_a_refresh_transition_restarts_the_delay_by_minting_a_new_entry(self):
        # Restart semantics is structural, not a timer mode: production mints
        # a new entry instant [DR timers-keyed consequences].
        refresh = NetPath("refresh")
        net = Net(
            places=[Place(PENDING), Place(EXPIRED)],
            transitions=[Transition(refresh), Transition(EXPIRE, timers=(Delay(10),))],
            arcs=[Arc(PENDING, refresh), Arc(refresh, PENDING), Arc(PENDING, EXPIRE), Arc(EXPIRE, EXPIRED)],
        )
        instance = Instance(net, Marking({PENDING: (Token.black(),)}))
        assert instance.next_maturation == 10
        firing = instance.step(at=5)  # only refresh is enabled: expire is immature
        assert firing is not None and firing.transition == refresh
        assert instance.next_maturation == 15
