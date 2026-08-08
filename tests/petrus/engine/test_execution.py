"""Engine execution, clock observation, and local Sensor behavior."""

from __future__ import annotations

import pytest

from petrus.motus.activity import ActivityInvocation
from petrus.motus.dispatch import InMemoryDispatch, InlineDispatch
from petrus.engine import Delivery, DriveOutcome, Engine, SimulatedClock
from petrus.impetus.history import ActivityCompleted, ExternalEventDelivered, FiringFailed, TimerMatured
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.instance import Status
from petrus.impetus.petrinet import Arc, Cel, Delay, Marking, Net, NetPath, Place, Token, Transition, Until

A, B, C, T = NetPath("a"), NetPath("b"), NetPath("c"), NetPath("t")
SRC = NetPath("src")


def _line_net(handler: str | None = None) -> Net:
    return Net(
        places=[Place(A), Place(B)],
        transitions=[Transition(T, handler=handler)],
        arcs=[Arc(A, T), Arc(T, B)],
    )


def _expiry_net(*timers) -> Net:
    return Net(
        places=[Place(A), Place(B)],
        transitions=[Transition(T, timers=timers)],
        arcs=[Arc(A, T), Arc(T, B)],
    )


def _ingress_net() -> Net:
    return Net(
        places=[Place(A), Place(B)],
        transitions=[Transition(SRC), Transition(T)],
        arcs=[Arc(SRC, A), Arc(A, T), Arc(T, B)],
    )


def _scripted(*rounds):
    remaining = list(rounds)

    def sensor():
        assert remaining, "sensor consulted past its script"
        return remaining.pop(0)

    return sensor


def _advance_until_rest(engine: Engine) -> DriveOutcome:
    firings = []
    while True:
        outcome = engine.advance()
        firings.extend(outcome.firings)
        if not outcome.ready:
            return DriveOutcome(tuple(firings), outcome.waiting, next_maturation=outcome.next_maturation)


class TestSimulatedClock:
    def test_now_starts_at_the_construction_instant(self):
        assert SimulatedClock().now() == 0
        assert SimulatedClock(at=7).now() == 7

    def test_observe_jumps_without_rewinding(self):
        clock = SimulatedClock(at=7)

        assert clock.observe(10) == 10
        assert clock.observe(4) == 10
        assert clock.now() == 10


class TestEngineDrivesTheSeam:
    def test_typed_place_rejects_an_incompatible_initial_token_before_history_is_written(self):
        net = Net(
            places=[Place(A, color="Expected")],
            transitions=[],
            arcs=[],
        )
        history = InMemoryHistoryStore()

        with pytest.raises(ValueError, match="initial marking.*place a.*Expected.*Other"):
            Engine.create(
                net,
                "invalid-initial-marking",
                history=history,
                dispatch=InMemoryDispatch(),
                marking=Marking({A: (Token("Other"),)}),
            )

        assert len(history) == 0

    def test_pumping_one_action_turns_drives_a_pure_chain_to_quiescence(self):
        token = Token("X")
        step = NetPath("step")
        net = Net(
            places=[Place(A), Place(B), Place(C)],
            transitions=[Transition(T), Transition(step)],
            arcs=[Arc(A, T), Arc(T, B), Arc(B, step), Arc(step, C)],
        )
        engine = Engine.create(
            net,
            "pure-chain",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (token,)}),
        )

        outcome = _advance_until_rest(engine)

        assert [firing.transition for firing in outcome.firings] == [T, step]
        assert [firing.occurrence for firing in outcome.firings] == [1, 2]
        assert engine.marking == Marking({C: (token,)})
        assert engine.status is Status.TERMINATED

    def test_an_activity_invocation_executes_through_inline_dispatch(self):
        consulted = []

        class Charge:
            def prepare(self, binding):
                return ActivityInvocation("charge", input={"n": 1})

            def project(self, binding, result):
                return {B: (Token("X", result),)}

        def recording(invocation, *, context):
            del context
            consulted.append(invocation)
            return {"ok": True}

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _line_net(handler="price"),
            "activity",
            history=history,
            dispatch=InlineDispatch({"charge": recording}),
            marking=Marking({A: (Token("X"),)}),
            handlers={"price": Charge()},
        )

        _advance_until_rest(engine)

        assert consulted == [
            ActivityInvocation(
                "charge",
                input={"n": 1},
                policy=consulted[0].policy,
                correlation="occurrence-1",
                idempotency="occurrence-1",
            )
        ]
        assert any(isinstance(record, ActivityCompleted) for record in history)
        assert engine.marking == Marking({B: (Token("X", {"ok": True}),)})

    def test_a_pure_projection_never_touches_dispatch(self):
        class ForbiddenDispatch(InMemoryDispatch):
            def dispatch(self, occurrence, invocation):
                raise AssertionError("a pure projection reached Dispatch")

        price = lambda binding, outputs: {B: (Token("X"),)}  # noqa: E731
        engine = Engine.create(
            _line_net(handler="price"),
            "pure-projection",
            history=InMemoryHistoryStore(),
            dispatch=ForbiddenDispatch(),
            marking=Marking({A: (Token("X"),)}),
            handlers={"price": price},
        )

        _advance_until_rest(engine)

        assert engine.marking == Marking({B: (Token("X"),)})

    def test_firing_records_are_stamped_from_the_engine_clock(self):
        engine = Engine.create(
            _line_net(),
            "clock-stamp",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("X"),)}),
            clock=SimulatedClock(at=5),
        )

        outcome = _advance_until_rest(engine)

        [firing] = outcome.firings
        assert all(record.instant == 5 for record in firing.records)


class TestEngineObservesTimers:
    def test_simulated_time_matures_and_fires(self):
        token = Token("X")
        engine = Engine.create(
            _expiry_net(Delay(10)),
            "timer",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (token,)}),
        )

        outcome = _advance_until_rest(engine)

        assert [firing.transition for firing in outcome.firings] == [T]
        assert TimerMatured(maturation_instant=10, instant=10) in engine.records
        assert engine.marking == Marking({B: (token,)})

    def test_repeated_delays_anchor_on_each_production(self):
        token = Token("X")
        second = NetPath("second")
        net = Net(
            places=[Place(A), Place(B), Place(C)],
            transitions=[Transition(T, timers=(Delay(5),)), Transition(second, timers=(Delay(5),))],
            arcs=[Arc(A, T), Arc(T, B), Arc(B, second), Arc(second, C)],
        )
        engine = Engine.create(
            net,
            "repeated-timers",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (token,)}),
        )

        _advance_until_rest(engine)

        assert [record for record in engine.records if isinstance(record, TimerMatured)] == [
            TimerMatured(maturation_instant=5, instant=5),
            TimerMatured(maturation_instant=10, instant=10),
        ]

    def test_until_matures_at_its_declared_instant(self):
        engine = Engine.create(
            _expiry_net(Until(100)),
            "until",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("X"),)}),
        )

        _advance_until_rest(engine)

        assert TimerMatured(maturation_instant=100, instant=100) in engine.records

    def test_a_late_observation_is_harmless_and_an_early_one_fails_loud(self):
        class Clock:
            def __init__(self, adjustment):
                self.at = 0
                self.adjustment = adjustment

            def now(self):
                return self.at

            def observe(self, instant):
                self.at = instant + self.adjustment
                return self.at

        late = Engine.create(
            _expiry_net(Delay(10)),
            "late",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("X"),)}),
            clock=Clock(3),
        )
        _advance_until_rest(late)
        assert TimerMatured(maturation_instant=10, instant=13) in late.records

        early_history = InMemoryHistoryStore()
        early = Engine.create(
            _expiry_net(Delay(10)),
            "early",
            history=early_history,
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("X"),)}),
            clock=Clock(-1),
        )
        with pytest.raises(ValueError, match=r"observed 9, before the requested maturation 10"):
            early.advance()


class TestTerminalFailure:
    def test_a_raising_pure_handler_records_failure_and_poisons_the_engine(self):
        def explode(binding, outputs):
            raise RuntimeError("quote service down")

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _line_net(handler="price"),
            "failure",
            history=history,
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("X"), Token("X"))}),
            handlers={"price": explode},
        )

        with pytest.raises(RuntimeError, match="quote service down"):
            engine.advance()

        assert isinstance(history.records[-1], FiringFailed)
        assert "quote service down" in history.records[-1].error
        with pytest.raises(RuntimeError, match="poisoned"):
            engine.advance()


class TestDelivery:
    def test_normalizes_source_tokens_and_identity(self):
        token = Token("X")
        delivery = Delivery("src", token, identity="evt-9")

        assert delivery.source == SRC
        assert delivery.tokens == (token,)
        assert delivery.identity == "evt-9"

    def test_rejects_a_string_payload_and_snapshots_a_sequence(self):
        with pytest.raises(ValueError, match=r"tokens must be a Token or a sequence of Tokens"):
            Delivery(SRC, "clean")

        delivery = Delivery(SRC, [Token("X"), Token("Y")])
        assert delivery.tokens == (Token("X"), Token("Y"))


class TestEngineSenses:
    def test_sensed_delivery_interleaves_with_internal_work(self):
        token = Token("X")
        engine = Engine.create(
            _ingress_net(),
            "sensed",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            sensor=_scripted([Delivery(SRC, token)], [], []),
        )

        outcome = _advance_until_rest(engine)

        assert [firing.transition for firing in outcome.firings] == [SRC, T]
        assert engine.marking == Marking({B: (token,)})

    def test_sensed_redelivery_is_acknowledged_once(self):
        token = Token("X")
        redelivered = Delivery(SRC, token, identity="evt-9")
        engine = Engine.create(
            _ingress_net(),
            "redelivery",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            sensor=_scripted([redelivered], [redelivered], []),
        )

        _advance_until_rest(engine)

        events = [record for record in engine.records if isinstance(record, ExternalEventDelivered)]
        assert [event.identity for event in events] == ["evt-9"]

    def test_sensor_decline_returns_control_and_a_sealed_engine_never_consults(self):
        awaiting = Engine.create(
            _ingress_net(),
            "awaiting",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            sensor=_scripted([]),
        )
        assert _advance_until_rest(awaiting).firings == ()
        assert awaiting.status is Status.AWAITING

        def never():
            raise AssertionError("consulted with nothing armed")

        sealed = Engine.create(
            _ingress_net(),
            "sealed",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            sensor=never,
        )
        sealed.seal(SRC)
        assert _advance_until_rest(sealed).firings == ()
        assert sealed.status is Status.TERMINATED

    def test_completed_status_does_not_disable_an_armed_sensor(self):
        token = Token("X")
        net = Net(
            places=[Place(A)],
            transitions=[Transition(SRC)],
            arcs=[Arc(SRC, A)],
            completion=Cel("size(a) != 0"),
        )
        statuses = []
        engine = None

        def sensor():
            statuses.append(engine.status)
            return [Delivery(SRC, token)] if len(statuses) == 1 else []

        engine = Engine.create(
            net,
            "completed-sensor",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            sensor=sensor,
        )
        _advance_until_rest(engine)

        assert statuses == [Status.AWAITING, Status.COMPLETED]
        assert engine.status is Status.COMPLETED

    def test_available_ingress_interrupts_a_pending_timer_once(self):
        clock = SimulatedClock()
        net = Net(
            places=[Place(A), Place(B)],
            transitions=[Transition(SRC), Transition(T, timers=(Delay(10),))],
            arcs=[Arc(SRC, A), Arc(A, T), Arc(T, B)],
        )
        engine = Engine.create(
            net,
            "timer-ingress",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("X"),)}),
            clock=clock,
            sensor=_scripted([Delivery(SRC, Token("X"), identity="evt-1")], []),
        )

        first = engine.advance()
        assert clock.now() == 0
        second = engine.advance()

        assert [firing.transition for firing in first.firings] == [SRC]
        assert second.ready is True
        assert clock.now() == 10

    def test_sensed_delivery_is_stamped_from_the_clock_and_matches_direct_delivery(self):
        token = Token("X")
        sensed_history = InMemoryHistoryStore()
        sensed = Engine.create(
            _ingress_net(),
            "parity-sensed",
            history=sensed_history,
            dispatch=InMemoryDispatch(),
            clock=SimulatedClock(at=5),
            sensor=_scripted([Delivery(SRC, token)], [], []),
            at=5,
        )
        _advance_until_rest(sensed)

        manual_history = InMemoryHistoryStore()
        manual = Engine.create(
            _ingress_net(),
            "parity-sensed",
            history=manual_history,
            dispatch=InMemoryDispatch(),
            clock=SimulatedClock(at=5),
            at=5,
        )
        manual.deliver(SRC, token)
        _advance_until_rest(manual)

        assert sensed_history.records == manual_history.records
        [event] = [record for record in sensed.records if isinstance(record, ExternalEventDelivered)]
        assert event.instant == 5

    def test_source_projection_runs_inline_and_a_failure_poisons(self):
        def explode(binding, outputs):
            raise RuntimeError("bad event")

        history = InMemoryHistoryStore()
        engine = Engine.create(
            Net(places=[Place(A)], transitions=[Transition(SRC, handler="ingest")], arcs=[Arc(SRC, A)]),
            "bad-source",
            history=history,
            dispatch=InMemoryDispatch(),
            handlers={"ingest": explode},
            sensor=_scripted([Delivery(SRC, Token("X"))]),
        )

        with pytest.raises(RuntimeError, match="bad event"):
            engine.advance()

        assert isinstance(history.records[-1], FiringFailed)


class TestEngineRefusesABrokenSensor:
    def test_none_is_not_an_empty_answer(self):
        engine = Engine.create(
            _ingress_net(),
            "none-sensor",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            sensor=lambda: None,
        )

        with pytest.raises(ValueError, match=r"sensor returned None: a sensor answers with a sequence"):
            engine.advance()

    def test_a_generator_answer_is_snapshotted(self):
        token = Token("X")
        rounds = []

        def sensor():
            rounds.append(len(rounds))
            return iter([Delivery(SRC, token)]) if len(rounds) == 1 else iter(())

        engine = Engine.create(
            _ingress_net(),
            "generator-sensor",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            sensor=sensor,
        )

        outcome = _advance_until_rest(engine)

        assert [firing.transition for firing in outcome.firings] == [SRC, T]
        assert rounds == [0, 1, 2]

    def test_a_raising_sensor_appends_nothing_and_poisons(self):
        def broken():
            raise RuntimeError("sensor exploded")

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "raising-sensor",
            history=history,
            dispatch=InMemoryDispatch(),
            sensor=broken,
        )
        before = history.records

        with pytest.raises(RuntimeError, match="sensor exploded"):
            engine.advance()

        assert history.records == before
        with pytest.raises(RuntimeError, match="poisoned"):
            engine.advance()
